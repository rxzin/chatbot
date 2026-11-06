# Chat

A private AI chat app. Users upload PDFs and text files to a conversation and ask
questions about them; replies stream in as they're written and show the sources they
used. The same chat also answers general questions, reports live weather, and turns bug
reports into Jira tickets after an admin approves them.

One FastAPI app serves both the API (under `/api`) and the built Next.js frontend, and
runs on FastAPI Cloud.

- [backend/README.md](backend/README.md): setup, settings, API and internals
- [frontend/README.md](frontend/README.md): setup, routes and structure
- [docs/PROGRESS.md](docs/PROGRESS.md): what's done and what's next
- [docs/design/chatbot-v2.md](docs/design/chatbot-v2.md): why things are built this way

## Features

- **Chat with streaming replies** over Server-Sent Events, with saved conversations.
- **Document answers (RAG):** uploads are split into chunks, embedded with
  `mistral-embed`, stored in Pinecone, reranked with Cohere, and cited as sources.
- **Agent with tools:** the model decides when to search the user's documents, search
  the web, check the weather, or file a bug report, and can use several tools before
  answering.
- **Web search** through Exa, with the pages it used shown as links.
- **Bug reports:** drafted from the conversation, queued for an admin, then created in
  Jira on approval with an email to the user.
- **Admin dashboard:** bug report approval, an audit log of every API request, and user
  and session management, including banning and revoking sessions.
- **Auth:** email and password, short-lived access tokens kept in memory, rotating
  refresh tokens in an HTTP-only cookie, instant revocation, and rate limits on login and
  sign-up.
- **Voice mode** in the browser, and a dark and light theme.

## Stack

| Layer | Tools |
|---|---|
| Model | Mistral `ministral-14b`, falling back to `ministral-8b` on rate limits and server errors |
| Retrieval | `mistral-embed`, Pinecone, Cohere rerank; Exa for web search |
| Backend | Python 3.14, FastAPI, LangGraph, SQLAlchemy (async), Alembic, uv |
| Data | PostgreSQL 18 (ids from `uuidv7()`), Redis |
| Frontend | Next.js 16 static export, React, Tailwind CSS v4, shadcn/ui, pnpm |
| Hosting | FastAPI Cloud, deployed by GitHub Actions on every push to `main` |

## How a message flows

```
Browser ──POST /api/chat──▶ FastAPI ──▶ LangGraph:  agent ⇄ tools (up to 4 rounds)
                                                      │      search_documents
                                                      │      web_search
                                                      │      get_weather
                                                      │      report_bug
Browser ◀──── SSE events ◀── runner ◀─────────────────┘
                               └─ saves the turn to Postgres and the recent context to Redis
```

## Run it locally

You need Python 3.14 with [uv](https://docs.astral.sh/uv/), Node.js 24 with pnpm,
PostgreSQL 18, Redis, and API keys for Mistral, Cohere and Pinecone.

**Backend** (see [backend/README.md](backend/README.md) for `.env`):

```bash
cd backend/app
uv sync
uv run alembic upgrade head
uv run python seed.py
uv run fastapi dev main.py        # http://localhost:8000
```

**Frontend:**

```bash
cd frontend/Chatbot
pnpm install
pnpm dev                          # http://localhost:3000
```

**Or with Docker Compose**, which starts Postgres and Redis, runs the migrations and the
seed, then the backend:

```bash
docker compose --env-file ./backend/app/.env up -d --build backend
# add the frontend container too:
docker compose --env-file ./backend/app/.env --profile local up -d
```

## Deploy

Pushing to `main` runs `.github/workflows/deploy.yml`, which calls `deploy.sh`. It needs
three repository secrets: `ENV_PRODUCTION` (the whole of `backend/app/.env.production`),
`FASTAPI_CLOUD_TOKEN` and `FASTAPI_CLOUD_APP_ID`.

To deploy by hand, put `FASTAPI_CLOUD_APP_ID=<app id>` in `backend/app/.env.production`
(or export it), then:

```bash
./deploy.sh                          # frontend, database and upload
./deploy.sh --no-db                  # skip migrations and the seed
./deploy.sh --no-frontend --no-db    # backend code only
```

`deploy.sh` builds the frontend into `backend/app/frontend_build`, runs migrations and the
seed against the production database, and uploads the app. The running app reads its
settings from the FastAPI Cloud dashboard, so change them there too.

## Project structure

```
backend/app/        FastAPI app: api/, auth/, core/, schemas/, services/, alembic/
frontend/Chatbot/   Next.js app: app/, components/, hooks/, lib/
docs/               Progress and design notes
deploy.sh           Build, migrate and upload to FastAPI Cloud
docker-compose.yml  Local stack only
```
