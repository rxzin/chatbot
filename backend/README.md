# Chat backend

The FastAPI app. It serves the API under `/api`, the health check at `/health`, and the
built frontend at `/`. The code lives in [`app/`](app/).

## Setup

Requires Python 3.14, [uv](https://docs.astral.sh/uv/), PostgreSQL 18 and Redis.

```bash
cd backend/app
uv sync
# create .env, see below
uv run alembic upgrade head      # create or update tables
uv run python seed.py            # roles, permissions and the admin user; safe to rerun
uv run fastapi dev main.py       # http://localhost:8000, docs at /docs
```

With Docker instead, see the root README; `docker-compose.yml` runs migrate, then seed,
then the backend on each start.

## Settings (`app/.env`)

All settings are in [`core/config.py`](app/core/config.py). These have no default and must
be set:

```bash
MISTRAL_API_KEY=
COHERE_API_KEY=
PINECONE_API=
EXA_API_KEY=                      # optional; empty turns web search off
VECTOR_STORE_PROVIDER=pinecone
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=                   # a long random string

POSTGRESQL_USERNAME=postgres
POSTGRESQL_PASSWORD=
POSTGRESQL_SERVER=localhost
POSTGRESQL_DATABASE=chatbot

ADMIN_EMAIL=                      # created by seed.py
ADMIN_PASSWORD=

JIRA_DOMAIN=                      # your-site.atlassian.net
JIRA_EMAIL=
JIRA_API_TOKEN=
JIRA_PROJECT_KEY=
JIRA_ISSUE_TYPE=Bug
BUG_REPORT_RATE_LIMIT_SECONDS=300
```

Commonly changed optional settings:

| Setting | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `local` | `local`, `staging` or `production` |
| `CORS_ORIGINS` | `[]` | JSON list, e.g. `["http://localhost:3000"]`. Not needed in production, where the frontend is on the same origin |
| `MISTRAL_MODEL` / `MISTRAL_FALLBACK_MODEL` | `ministral-14b-latest` / `ministral-8b-latest` | Change `MODEL_INPUT_TOKEN_LIMIT` and `MODEL_OUTPUT_TOKEN_LIMIT` with them |
| `PINECONE_INDEX_NAME` | `documents-mistral-embed` | Created on startup if missing, 1024 dimensions |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | empty | Emails are skipped when empty |
| `SEARCH_PROVIDER` | `exa` | `none` turns web search off. So does an empty `EXA_API_KEY` |
| `WEB_SEARCH_RESULTS` / `WEB_SEARCH_DAILY_LIMIT_PER_USER` | `5` / `30` | Results per search, and searches per user per UTC day |
| `AGENT_MAX_TOOL_ROUNDS` / `AGENT_MAX_CALLS_PER_ROUND` | `4` / `4` | |
| `ALLOW_PUBLIC_REGISTRATION` | `true` | |
| `REGISTRATION_MAX_GLOBAL` / `REGISTRATION_MAX_PER_IP` | `100` / `10` | Per `REGISTRATION_RATE_LIMIT_SECONDS` (an hour) |
| `LOGIN_MAX_FAILURES_PER_ACCOUNT` / `_PER_IP` | `10` / `50` | Per `LOGIN_RATE_LIMIT_WINDOW_SECONDS` (15 minutes) |
| `TRUST_PROXY_HEADERS` | `false` | Turn on only when a trusted proxy sets `X-Real-IP`. Per-IP limits are off without it |
| `AUDIT_RETENTION_DAYS` | `90` | |
| `MAX_UPLOAD_BYTES` | 10 MB | |

## API

Interactive docs are at `/docs`. All routes except health are under `/api`.

| Area | Routes |
|---|---|
| Health | `GET /health/` |
| Auth | `POST /auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/clear-session`; `GET /auth/me` |
| Chat | `POST /chat` (SSE stream) |
| Conversations | `GET`, `POST /conversations`; `GET /conversations/{id}`; `GET /conversations/{id}/messages` |
| Documents | `POST /conversations/{id}/documents/upload`; `GET /conversations/{id}/documents`; `DELETE /conversations/{id}/documents/{document_id}` |
| Admin: bugs | `GET /admin/pending-tickets`; `POST /admin/approve-ticket/{id}`, `/admin/reject-ticket/{id}` |
| Admin: audit | `GET /admin/summary`, `/admin/audit-logs` |
| Admin: users | `GET /admin/users`, `/admin/users/{id}/sessions`; `DELETE /admin/sessions/{id}`; `POST /admin/users/{id}/revoke-sessions`, `/ban`, `/unban` |

Admin routes check permissions (`ticket:manage`, `audit:read`, `users:ban` and others),
which `seed.py` grants to the admin role.

## How chat works

`POST /api/chat` runs a LangGraph graph ([`services/graph/`](app/services/graph/)) and
streams its output as SSE:

1. **`runner.prepare_context`** loads the conversation's indexed documents and its recent
   messages from Redis. On a cold cache it rebuilds them from Postgres.
2. **`agent`** streams the model's reply. The model may instead ask for tools, which
   **`tools`** runs before going back to `agent`
   ([`services/graph/tools.py`](app/services/graph/tools.py)):
   - `search_documents(query)`: searches Pinecone, reranks with Cohere, and returns
     passages with their sources. Only offered when the conversation has indexed
     documents.
   - `web_search(query)`: searches the web with Exa
     ([`services/search.py`](app/services/search.py)) and returns short excerpts with
     their URLs. Offered when a search provider is set up. Each user gets
     `WEB_SEARCH_DAILY_LIMIT_PER_USER` searches a day.
   - `get_weather(city)`: current weather and forecast from Open-Meteo.
   - `report_bug(title, description)`: saves a ticket for admin approval. Limited per
     user by `BUG_REPORT_RATE_LIMIT_SECONDS`.

   After `AGENT_MAX_TOOL_ROUNDS` rounds (4) the model must answer without tools. Tool
   failures go back to the model as error results, never as exceptions. Web pages are
   untrusted, so `report_bug` is withdrawn for the rest of a turn once the web has been
   searched, and only `http` and `https` links are kept.
3. **`runner`** turns the graph's output into SSE events, then saves the turn to Postgres
   and the trimmed recent context to Redis.

Each `data:` line is one JSON event ([`schemas/chat.py`](app/schemas/chat.py)):

| Event | Fields | When |
|---|---|---|
| `text-delta` | `delta` | Each piece of the reply, in order |
| `tool-start` | `toolCallId`, `toolName`, `input` | The agent started a tool |
| `tool-result` | `toolCallId`, `toolName`, `isError` | That tool finished. Its output goes to the model only |
| `sources` | `sources`, `webSources` | Once, before `done`, when documents or the web were searched |
| `done` | `finishReason` | The reply finished. A stream without it was interrupted |
| `error` | `error.code`, `error.message` | The reply failed; nothing is saved |

Messages store `content` (plain text, used for the model's memory) and `parts`, the
display content in order: `text` and `sources` parts. Sources therefore survive a reload.
Messages saved before `parts` existed are returned as a single text part.

Mistral calls go through [`services/fallback.py`](app/services/fallback.py), which retries
on the fallback model if the main one fails before any text has streamed. A reply cut off
at `MODEL_OUTPUT_TOKEN_LIMIT` ends with a note telling the user to say "continue".

Long conversations are summarised once they pass `SUMMARIZE_THRESHOLD` of the input limit
([`services/context_budget.py`](app/services/context_budget.py)).

## Documents

Uploads (`.pdf` or `.txt`, up to `MAX_UPLOAD_BYTES`) return straight away and are indexed in
the background: split into parent chunks of `PARENT_CHUNK_SIZE_TOKENS`, embedded with
`mistral-embed`, and stored in Pinecone with the conversation's id. A document's status
goes from `processing` to `indexed` or `failed`, and only indexed documents are searched.

## Data

- **Postgres:** users, roles and permissions, sessions, conversations, messages,
  documents, pending tickets and the audit log. Schema changes go through Alembic in
  [`alembic/versions/`](app/alembic/versions/).
- **Redis:** `chat:user:{user}:conversation:{id}` (recent messages),
  `…:summary`, `rate_limit:{action}:{user}`, `login_failures:*` and `registrations:*`.
- **Audit log:** a middleware records every `/api/*` request (no query strings or
  bodies) and deletes entries after `AUDIT_RETENTION_DAYS`.

## Structure

```
app/
  main.py            App, routers, middleware, and the frontend at /
  api/routes/        Chat, conversations, documents, admin, health
  auth/              Login, sessions, tokens, rate limits
  core/              Settings, database, logging, errors, middleware
  schemas/           SQLAlchemy models and Pydantic schemas
  services/          Mistral, fallback, memory, RAG, Jira, email, audit
  services/graph/    LangGraph graph (agent and tools nodes), tools and runner
  alembic/           Migrations
  seed.py            Roles, permissions and the admin user
```

Run `uv run python -m services.graph.visualize` to redraw `services/graph/graph.png`.
After changing a route or schema, run `pnpm run generate:api-types` in
`frontend/Chatbot` to update the frontend's types.
