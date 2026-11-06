# Chatbot v2 design

Status: in progress. Assumes a new deployment with one backend and hundreds of users
at most, so no scaling work is planned.

## Scope

**In scope**

- Mistral for chat and embeddings, with a model fallback
- Hardened authentication
- Mobile navbar fix and consistent shadcn styling, including the admin side
- Generated frontend types from the backend's OpenAPI schema
- Agent loop with tool calls instead of a one-shot classifier
- Web search through Exa, behind a provider interface
- AI Elements UI: inline citations, tool steps, suggested questions

**Out of scope**

- Reasoning output. Ministral rejects `reasoning_effort` with a 400, and Small 4 and
  Medium 3.5 returned 429 on this key.
- Migrating old data. This is a new deployment.

## Models

| Purpose | Model | Notes |
|---|---|---|
| Chat (main) | `ministral-14b-latest` | 262,144 token context |
| Chat (fallback) | `ministral-8b-latest` | Used on 429, 5xx and connection failures, before the first token only |
| Embeddings | `mistral-embed` | 1024 dimensions, Pinecone index `documents-mistral-embed` |

Observed limits on the test key: 30 requests per minute and 937,500 tokens per minute,
so requests run out first. Token counts stay as `tiktoken` estimates with a safety
margin. `mistral-common`'s `from_model` rejected all five current model names tried.

Embeddings have no runtime fallback, because vectors from different models are not
comparable. Changing the model means a new index and re-embedding every document.

## Authentication

- Access token: 15 minutes, kept in memory only, carries a `sid` claim that is checked
  against the session row on each request, so logout takes effect immediately.
- Refresh token: HttpOnly cookie scoped to `/auth`, rotated on each use. The session row
  keeps a stable ID across rotations.
- Reuse handling: the previous token within the grace period returns 409 and the client
  retries, because this is normally two tabs racing. Any other stale token revokes the
  session.
- Sessions end after 7 days idle or 30 days in total.
- Login attempts are limited in Redis per account, and per IP when
  `TRUST_PROXY_HEADERS=true`. Redis failures do not block login.
- Tabs serialize refreshes with `navigator.locks`.

## Admin dashboard

Tabs at `/admin`, shown per permission: bug reports (`ticket:manage`), audit log
(`audit:read`), and users and sessions (`users:ban`, `sessions:manage`).

- Audit log: one row per request with user, method, path, status, duration, IP and user
  agent. Query strings and bodies are never stored, because they can hold chat messages
  and passwords. Rows are written in batches by a background task and kept for 90 days
  (`AUDIT_RETENTION_DAYS`). Entries are dropped and logged if the queue fills up, so the
  API never waits on this table.
- Lists page with `uuidv7` ids as cursors, because those ids sort by time.
- Revoking a session deletes its row, which ends its access and refresh tokens on their
  next use. A reply already streaming finishes.
- Banning sets `is_active=false` and deletes all sessions in one transaction. Admins can't
  ban themselves or another admin, or revoke their own current session from here.

## Hosting

The whole app runs on FastAPI Cloud from one address, with no custom domain needed.

- FastAPI serves the static frontend with `app.frontend()`, and the API lives under `/api`.
  Pages and API share an origin, so the refresh cookie works and CORS isn't needed.
- Only `/api/*` is written to the audit log, so page and asset requests don't flood it.
- Logs go to stdout only. Postgres 18 or newer (for `uuidv7()`) and Redis run elsewhere.

To deploy:

1. Set environment variables in FastAPI Cloud, with `ENVIRONMENT=production`.
2. Run `alembic upgrade head` and `seed.py` against production before deploying code that
   needs them. FastAPI Cloud has no documented pre-start step.
3. In `frontend/Chatbot`, run `npm run build:deploy`, which copies the build to
   `backend/app/frontend_build`. `fastapi deploy` doesn't build the frontend.
4. In `backend/app`, run `fastapi deploy`. `.fastapicloudignore` keeps `.env` and `.venv` out
   of the upload and includes the generated frontend.

For local development, the frontend's `NEXT_PUBLIC_API_URL` is the backend's origin, such
as `http://localhost:8000`, without `/api`. A custom domain can be added later with little
or no code change.

Known risks on FastAPI Cloud, to check after the first deploy:

- Scale to zero is on by default. Document ingestion runs after the upload response, so an
  idle instance could stop before it finishes.
- The header carrying the real client IP is undocumented, so keep
  `TRUST_PROXY_HEADERS=false` until it is confirmed.
- SSE behavior and request timeouts are undocumented, so test streaming replies.
- `/chat` redirects to `/chat/`. Confirm that the redirect stays on `https` behind their
  proxy.
- Python 3.14 support is implied by their docs but not stated.

## Stream protocol

Built (2026-11-06): typed SSE events `text-delta`, `sources`, `done` and `error`, defined
as a discriminated union in `schemas/chat.py` and generated into the frontend's types.
Messages have a nullable `parts` JSONB column (`text` and `sources` parts), so sources
survive a reload; `content` keeps the plain text for the model's memory.

`tool-start` and `tool-result` were added with the agent loop, and `suggestions` (event
and part) with feature 4. Sources carry a `number` for inline citations. Each adds an event type and, where it should survive
a reload, a part type.

## Agent

Built (2026-11-06) with `search_documents`, `get_weather`, `report_bug` and
`web_search` (Exa, added with feature 3; see below). `agent` and `tools` are LangGraph nodes; the cap is
`AGENT_MAX_TOOL_ROUNDS` (4) and calls per round are capped at
`AGENT_MAX_CALLS_PER_ROUND` (4). Tool steps stream as `tool-start` and `tool-result`
events but aren't saved as parts yet. Suggestions are not built.

```
agent (LLM + tools) ──tool calls──> run tools ──> back to agent
        └── no tool calls ──> final answer ──> suggestions ──> persist
```

- Tools: `search_documents` (only when documents exist), `get_weather`, `report_bug`,
  `web_search`.
- The loop is capped at about 4 steps, then forced to answer with `tool_choice="none"`.
- `SearchProvider` interface with `ExaSearchProvider`, selected by `SEARCH_PROVIDER`.
- Web pages are untrusted input. Disable `report_bug` after a web search, limit query
  length, set per-user quotas, allow only `http` and `https` citation links, and leave
  out a `fetch_url` tool.

Web search, as built: `services/search.py` holds the `SearchProvider` interface and
`ExaSearchProvider` (`type: auto`, highlights of up to 1,200 characters per page, so the
model reads excerpts rather than whole pages). All five protections above are in place;
queries are capped at 500 characters and the quota is 30 a day per user. Web sources are
saved as `webSources` on the `sources` part.

## Frontend

- Own `useChat` and SSE stream, no AI SDK. AI Elements are copied in and adapted.
- Types generated with `openapi-typescript` into `types/api.ts`. A shared folder does not
  work, because Python cannot import TypeScript and the frontend's Docker build context
  is `frontend/Chatbot`.
- Route groups `(marketing)`, `(auth)` and `(app)`, with no larger reorganization.

## Decisions

| Decision | Solves | Worsens | Change it when… |
|---|---|---|---|
| `sid` check against Postgres | Immediate logout | One more lookup per request | Auth queries become a top latency cost |
| Access token in memory | XSS can't read it from storage | One refresh per page load | Refresh volume becomes a measurable cost |
| Per-account login limit | Password guessing | An attacker can lock an account for 15 minutes | Lockouts are reported by real users |
| Agent loop replaces classifier | Misrouting; multi-step answers | 2–3 LLM calls per turn | Cost per turn exceeds budget |
| Own web search tool | Works with any LLM; own citations | Another vendor and key | Upkeep exceeds Mistral connector fees |
| Same-provider fallback | Per-model limits and capacity errors | No cover for a Mistral outage | A Mistral outage causes real downtime |
| Own SSE events, no AI SDK | Keeps the working stream and LangGraph | Protocol maintained in-house | Several AI SDK features would need rebuilding |
| Generated types | Stops frontend and backend drifting | One generation step | A second client needs the same API |
| Frontend served by FastAPI, on one address | No domain, proxy or CORS needed; one deploy | Frontend must be built before each deploy; a platform outage takes down everything | Deploys need previews, or the frontend needs server rendering |
| Audit rows in Postgres, batched | Searchable in the dashboard with no new service | Table grows with traffic; possible gaps under extreme load | Purges slow the database, or an audit log must be complete for compliance |

## Build order

1. Auth fixes and navbar
2. shadcn cleanup, folder changes, generated types
3. Stream events and `parts` storage, keeping today's graph
4. Agent loop with the existing tools
5. Web search and inline citations
6. Suggested questions

## Weakest points

- **Tool permissions:** web content can steer a model that also has private documents and
  a ticket-creating tool. New tools with side effects should need human approval, as
  `report_bug` already does through the admin queue.
- **Shared request budget:** if chat and embeddings share a limit, a large upload can
  block chat. The next move is a paid tier or a shared limiter in Redis.
