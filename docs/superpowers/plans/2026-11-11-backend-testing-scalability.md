# Backend Testing Infrastructure & Distributed Scalability Benchmarking — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the FastAPI backend an isolated pytest suite (real Postgres + Redis, faked AI providers), reproducible k6 benchmarks, and a three-phase scaling comparison (1 API + Postgres → 2 API + 5-node CockroachDB → 3 API + 5-node CockroachDB) with failure experiments and a measured report.

**Architecture:** Tests live in `backend/app/tests/` (the uv project root) and run the real app in-process over ASGI against a disposable Postgres 18 + Redis 7 from `docker-compose.test.yml`. One config switch (`EXTERNAL_SERVICES=fake`) replaces Mistral, Pinecone and Cohere at the lifespan seam; the same switch powers the mocked-agent k6 benchmarks. Benchmark stacks live in `infra/bench/` as separate compose projects, always behind nginx, with fixed CPU/memory limits and a Python runner that stores every result under `bench/results/`.

**Tech Stack:** pytest, pytest-asyncio, pytest-cov, respx, asgi-lifespan, HTTPX, Grafana k6 v2.3.0, Docker Compose v5, Postgres 18, Redis 7, nginx, HAProxy, CockroachDB, `sqlalchemy-cockroachdb`.

**Spec:** the brief "Backend Testing Infrastructure & Distributed Scalability Benchmarking" (sections §1–§10 are cited below). Save it as `docs/superpowers/specs/2026-11-11-backend-testing-scalability-brief.md` so it travels with this plan.

**How to read this file:** The order is A, B, C, D, X, E, F, G, H. Each phase ends with something that runs, so you can stop after any of them. Phase X holds the four app changes you decided on (2026-11-11); it sits after the tests that protect them and before the first benchmark, so every benchmark phase runs the same code. Phase F starts with a gate (F1) that can change the tasks after it.

---

## Global Constraints

- Existing API contracts stay unchanged; the only addition is an optional `Idempotency-Key` request header. New settings default to today's behavior.
- App behavior changes only in Phase X (Argon2 hashing, chat during a Redis outage, idempotency, switchable id strategy). Phases A–D change no behavior.
- Postgres integration tests use real Postgres 18 (`postgres:18-alpine`, same as `docker-compose.yml`). No SQLite.
- Automated tests never call Mistral, Pinecone, Cohere, Exa, Jira, Open-Meteo, Langfuse or SMTP.
- Test, benchmark, dev and production config stay separate: tests read only `tests/test.env`, benchmarks only `infra/bench/bench.env`. Neither reads `backend/app/.env`.
- CockroachDB appears only from Phase F on. Phase E (the baseline) is Postgres only.
- Destructive scripts (truncate, flush, kill) run only against compose projects named `chatbot-test`, `chatbot-bench-p1`, `chatbot-bench-crdb` on `127.0.0.1`.
- No production data anywhere. Benchmark data is synthetic and seeded by script.
- The report contains measured numbers only. An unmeasured cell reads `not measured`.
- Held constant across Phases 1–3: k6 scripts and payloads, profiles, warm-up, dataset (200 users × 5 conversations × 20 messages), per-container limits, `bench.env`, backend image, nginx in front, random ids (`ID_STRATEGY=random`), Argon2 parameters.
- Required commands (run from `backend/app`): `uv run pytest tests -v --cov=. --cov-report=term-missing`, `uv run pytest tests/integration -v`, `uv run pytest tests/concurrency -v`.

## Review Focus

Things the spec implies but does not spell out, most likely first. Each has a test in the task named.

1. **Tests pointed at a real database.** An exported shell variable (`POSTGRESQL_SERVER`, `REDIS_URL`) beats the env file, so a truncate could hit dev data. Expect: the suite refuses to start. → Task A3, `test_guard_*`.
2. **Real provider keys leaking into tests.** `env_ignore_empty=True` means an empty variable cannot blank a key from `.env`. Expect: tests see only dummy keys and tracing off. → Task A2, `test_settings_ignore_dev_env_file`.
3. **A client that disconnects right at `done`.** The turn is saved *after* `done` is sent and skipped if the client has gone (`runner.py:253`). Expect: documented, and k6/tests read to end-of-stream. → Task C2, `test_disconnect_after_done_loses_turn`.
4. **Access tokens expiring mid-benchmark.** Tokens live 15 minutes; a longer run turns into 401s that look like capacity failures. Expect: the k6 helper re-logs in after 10 minutes. → Task E2, smoke check.
5. **Benchmarks on a dirty dataset.** Write workloads grow tables and leave Redis keys, so run 2 is not run 1. Expect: the runner rebuilds the stack and records row counts. → Task E4, `meta.json` assertion.

---

## Findings from the codebase (spec §1)

Read these before starting; the tasks refer to them as F-numbers.

**Lifecycle and globals**

- **F1** `core/config.py:14` always loads `backend/app/.env`, which holds real keys. See Review Focus 2.
- **F2** Import-time globals: `core/database.py:10-18` (engine, `SessionLocal`), `auth/handler.py:6-8` (`SECRET_KEY`), `main.py:25`, `auth/service.py:27` (a bcrypt hash). Environment must be set before the first app import.
- **F3** `SessionLocal` is imported directly by `services/graph/runner.py`, `services/streaming.py`, `services/audit.py`, `services/usage.py`, `services/graph/tools.py`, `services/documents.py`, and `api/routes/health.py` imports `engine`. Overriding `get_db` would isolate only half the app, so tests point the whole process at the test database instead.
- **F4** `core/lifespan.py:61-63` calls Pinecone over the network at startup, and `:53` pings Redis. The app cannot start offline.
- **F5** Mistral's SDK uses `httpx2` and Pinecone uses `aiohttp`, so respx (which patches `httpx`) cannot intercept them. respx covers Jira, Open-Meteo and Exa; the others need fakes.
- **F6** No pool sizing on the engine (SQLAlchemy default 5 + 10 overflow per process).
- **F7** `config.py:120` hard-codes the `postgresql+asyncpg` scheme.

**Behavior worth pinning down**

- **F8** bcrypt runs synchronously inside async handlers (`auth/security.py`), default cost 12. Login and registration block the event loop for the length of one hash, which stalls every other request on that instance. The password is hashed once, directly by bcrypt; there is no pre-hash step (the SHA-256 in `hash_token` is for refresh tokens only). → Task X1.
- **F9** Limits that will distort benchmarks if left alone: `REGISTRATION_MAX_GLOBAL=100`/hour, `CHAT_DAILY_LIMIT_PER_USER=200`, login failure caps.
- **F10** The turn is persisted after `done`, inside the stream generator, and skipped on disconnect (`runner.py:250-268`). An exception there is caught by the same `except` and emits `error` after `done`.
- **F11** `save_turn` swallows database errors and returns `False` (`services/message.py:63`). The client is never told.
- **F12** Redis down: `consume_daily_quota` returns `False`, so `/api/chat` answers 429 (fails closed), while login limits fail open. `replace_history` swallows errors, so `set_conversation_state` reports success even when the write failed.
- **F13** No idempotency on `POST /api/chat` or `POST /api/conversations`. A retried request creates duplicates.
- **F14** `replace_history` is `DELETE` then `RPUSH` (`services/memory.py:137-146`), not atomic. Two turns in one conversation race; the last writer wins in Redis.
- **F15** `prune_user_sessions` reads then deletes without a lock (`auth/service.py:95`). Concurrent logins can exceed the session cap.
- **F16** `create_user_service` checks then inserts (`services/user.py:30`). A concurrent duplicate hits the unique index and returns 500, not 409.
- **F17** Document ingestion runs in `BackgroundTasks` from a local temp file. If that instance dies, the document stays `processing`.
- **F18** Audit rows are queued in memory and flushed every second. Tests must flush explicitly; a killed instance loses its queue.
- **F19** The health route is `/health/` (`/health` redirects with 307).
- **F25** `save_turn` inserts the user and model messages in one transaction, so both get the same `created_at` (`now()` is the transaction start). `list_messages` orders by `created_at` alone, so their order is not guaranteed. → Task X4.
- **F26** `admin_audit.py:79-83` and `admin_users.py:62-66,107` paginate by `id`, which is only correct while ids sort by time. → Task X4.
- **F27** The Redis client has no socket timeouts (`services/memory.py:17`), so an unreachable Redis can hang a request instead of failing. → Task X2.
- **F28** (found in Task X2) After a Redis outage, Redis still holds the pre-outage history list, so turns saved only to Postgres during the outage are invisible to the model once Redis returns. Pinned by `test_history_not_stale_after_outage` (xfail). Fix (compare with Postgres before trusting the cache) is a follow-up.

- **F29** (found in Task B3) A request with no `Authorization` header is rejected by FastAPI's `OAuth2PasswordBearer`, so its 401 body is `{"detail": "Not authenticated"}`. Every other error, including an invalid token, uses `{"success": false, "error": {"code", "message"}}`. Pinned by `test_no_token_is_rejected`; not changed.

- **F30** (found in Task D1) Concurrent chat streams exhaust the default DB pool (5 + 10 overflow). A chat request holds the `get_db` connection while its stream opens more through `SessionLocal`, so with about 16 or more simultaneous chats every connection is held by a request waiting for a second one, until the 30 s pool timeout raises `QueuePool limit ... reached`. 20 concurrent users chatting once each fails this way; 6 succeed. Pinned by `test_users_chatting_concurrently_never_see_each_others_messages` (6 users); the 20-user version is `xfail(F30)`. Not changed.

**Blocking the CockroachDB phases**

- **F20** Every table's id defaults to `uuidv7()` (`schemas/models.py`, 8 migrations). That is a Postgres 18 built-in. CockroachDB's UUID docs list only `gen_random_uuid()` and `uuid_v4()`, so migrations are expected to fail there. `admin_audit.py:75` also relies on ids sorting by time.
- **F21** Time-ordered ids are sequential keys. On CockroachDB every insert lands in the same range, which caps write scaling. This may be the main Phase 2/3 finding.
- **F22** `SELECT … FOR UPDATE` at `auth/service.py:182` and `api/routes/admin.py:40`. CockroachDB runs SERIALIZABLE by default and returns SQLSTATE 40001 under contention; the app has no retry.

**Repo hygiene**

- **F23** `.gitignore:20` is `tests/**`, which ignores every `tests` folder. `.env.*` is ignored too. Root `tests/test_llms_full.py` is a local, untracked file.
- **F24** The Docker image copies all of `backend/app`, so tests would ship in it.

## Decisions

Decided on 2026-11-11. D1 is still yours to write.

| # | Decision | Outcome | Task |
|---|----------|---------|------|
| D1 | What counts as a "safe" test target in the guard | A separate, dedicated Postgres instance (pgvector image) that is not the dev database. You write the ~10 lines; the rules are fixed in Task A3 Step 4. | A1, A3 |
| D2 | Chat when Redis is down | Chat keeps working. The daily chat quota is skipped during the outage; the paid web-search quota still refuses. | X2 |
| D3 | CockroachDB contention | Run CockroachDB at READ COMMITTED. It is Postgres's default, so the app's existing `FOR UPDATE` locks mean the same thing, and no retry code is needed. One labeled SERIALIZABLE run shows the difference. | F2, F3 |
| D4 | `Idempotency-Key` header | Added to `POST /api/chat` and `POST /api/conversations`, optional. A repeat returns the original result. | X3 |
| D5 | Id strategy | Random ids on CockroachDB. A setting (`ID_STRATEGY`) and a migration let Postgres run with random ids too, so all three phases compare like with like. | X4 |
| — | Password hashing | bcrypt replaced with Argon2id, hashed off the event loop. Existing bcrypt hashes keep working and are upgraded at next login. | X1 |

---

## File Structure

```
.gitignore                                  modify  (tests/** → /tests/**, bench raw output)
docker-compose.test.yml                     create  Postgres 18 + Redis 7 for pytest
backend/.dockerignore                       modify  exclude app/tests
backend/Dockerfile                          modify  optional UV_EXTRA_ARGS build arg
backend/app/.fastapicloudignore             modify  exclude tests/
backend/app/pyproject.toml                  modify  dev deps, bench group, pytest + coverage config
backend/app/core/config.py                  modify  APP_ENV_FILE, EXTERNAL_SERVICES, DB_*, FAKE_LLM_*
backend/app/core/database.py                modify  pool settings
backend/app/core/lifespan.py                modify  fake-services branch
backend/app/services/fakes.py               create  FakeLLM, FakeEmbeddingService, FakeVectorStore, FakeReranker
backend/app/auth/security.py                modify  Argon2id, legacy bcrypt verify, async wrappers        (X1)
backend/app/services/memory.py              modify  socket timeouts, fail-open quota, in-flight lock      (X2, X3)
backend/app/core/idempotency.py             create  Idempotency-Key header dependency                     (X3)
backend/app/core/ids.py                     create  id_server_default() for models and migrations         (X4)
backend/app/alembic/versions/               modify 8, create 2  (idempotency keys; id default follows strategy)
backend/app/api/routes/{streamchat,conversations,admin_audit,admin_users}.py   modify  (X2–X4)
backend/app/services/{conversation,message,streaming}.py, services/graph/runner.py   modify  (X3, X4)
backend/app/scripts/bench_seed.py           create  synthetic dataset
backend/app/tests/
  test.env, test.crdb.env                   create  dummy settings
  conftest.py                               create  env bootstrap, guard, fixtures
  support/{fakes,factories,sse,server}.py   create  ScriptedLLM, data builders, SSE parser, live server
  unit/                                     create  pure-function tests
  integration/                              create  API + Postgres + Redis tests, chat lifecycle
  agent/                                    create  SSE and agent-loop tests
  concurrency/                              create  race tests
  distributed/                              create  cross-instance + CockroachDB tests (skipped without a stack)
  load/{health,auth,database,conversations,chatbot}.js, lib/{config,auth,summary}.js, rates.json
infra/bench/
  bench.env, bench.crdb.env                 create
  compose.phase1.yml, compose.crdb.yml      create
  nginx/{phase1,phase2,phase3}.conf         create
  haproxy/haproxy.cfg                       create
  run_bench.py, chaos.py, ledger.py, report.py   create
bench/results/                              create  committed summaries; raw.csv.gz ignored
docs/testing.md, docs/multi-instance.md, docs/benchmarks/REPORT.md   create
```

Ports (all bound to 127.0.0.1): test Postgres 55432, test Redis 56379, bench nginx 58080, api1–3 58001–58003, bench Postgres 55433, bench Redis 56380, CockroachDB SQL via HAProxy 56257, CockroachDB console 58888.

---

# Phase A — Test foundation (spec §2, §5)

### Task A1: Tooling, ignore rules, test containers

**Files:**
- Modify: `.gitignore:20`, `backend/.dockerignore`, `backend/app/.fastapicloudignore`, `backend/app/pyproject.toml`
- Create: `docker-compose.test.yml`

**Interfaces:**
- Produces: compose project `chatbot-test` with services `db-test` (`127.0.0.1:55432`, user/password/database all `chatbot_test`) and `redis-test` (`127.0.0.1:56379`); pytest config used by every later task.

- [ ] **Step 1:** In `.gitignore`, replace `tests/**` with `/tests/**` (keeps your root scratch folder ignored, un-ignores `backend/app/tests`). Add `bench/results/**/raw.csv.gz`.
- [ ] **Step 2:** Add `app/tests` to `backend/.dockerignore` and `tests/` to `backend/app/.fastapicloudignore` (F24).
- [ ] **Step 3:** From `backend/app`: `uv add --dev pytest pytest-asyncio pytest-cov respx asgi-lifespan`.
- [ ] **Step 4:** Add to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"
asyncio_default_test_loop_scope = "session"
markers = ["distributed: needs a running bench stack (set STACK_URLS)"]

[tool.coverage.run]
omit = [".venv/*", "tests/*", "alembic/*", "frontend_build/*", "scripts/*", "services/graph/visualize.py"]
```

  One session-wide event loop is required: the engine pool and the Redis client are module-level and bound to the loop that first used them (F2).

- [ ] **Step 5:** Write `docker-compose.test.yml` with `name: chatbot-test`. `db-test`: `pgvector/pgvector:pg18` (D1; confirm the `pg18` tag pulls — it must be major version 18, because the schema needs `uuidv7()` and the spec requires the app's major version), `tmpfs: /var/lib/postgresql` (disposable), `pg_isready` healthcheck, port `127.0.0.1:55432:5432`. The app does not use the `vector` extension today (vectors live in Pinecone), so the image only has to behave as Postgres 18; do not `CREATE EXTENSION` in tests. `redis-test`: `redis:7-alpine`, `command: redis-server --save "" --appendonly no`, `redis-cli ping` healthcheck, port `127.0.0.1:56379:6379`.
- [ ] **Step 6: Verify.** `docker compose -f docker-compose.test.yml up -d --wait` exits 0 and `docker compose -f docker-compose.test.yml ps` shows both `healthy`. `git check-ignore backend/app/tests/conftest.py` prints nothing.
- [ ] **Step 7: Commit** `chore: add pytest tooling and isolated test containers`.

### Task A2: Make startup testable without external services

**Files:**
- Modify: `backend/app/core/config.py`, `backend/app/core/database.py`, `backend/app/core/lifespan.py`
- Create: `backend/app/services/fakes.py`, `backend/app/tests/test.env`, `backend/app/tests/unit/test_config.py`

**Interfaces:**
- Produces settings (defaults keep current behavior):
  - env var `APP_ENV_FILE` — path of the env file to load; unset means `backend/app/.env`.
  - `EXTERNAL_SERVICES: Literal["live", "fake"] = "live"`
  - `DB_SCHEME: Literal["postgresql+asyncpg", "cockroachdb+asyncpg"] = "postgresql+asyncpg"`, `DB_QUERY: str = ""` (appended as `?…`), `DB_POOL_SIZE: int = 5`, `DB_MAX_OVERFLOW: int = 10`
  - `FAKE_LLM_TOKEN_COUNT: int = 40`, `FAKE_LLM_TOKEN_DELAY_MS: int = 20`
- Produces in `services/fakes.py`:
  - `class FakeLLM(AIPlatform)` — `stream_turn` yields `f"fake-reply h={len(history)} "` then `FAKE_LLM_TOKEN_COUNT - 1` chunks of `"tok "`, sleeping `FAKE_LLM_TOKEN_DELAY_MS` between chunks, never tool calls; `_complete_text` returns `"Fake Title"`.
  - `class FakeEmbeddingService(EmbeddingService)` — deterministic vector of length `EMBEDDING_DIMENSION` derived from `sha256(text)`.
  - `class FakeVectorStore(VectorStoreService)` — in-memory `dict[(user_id, document_id)] -> list[VectorChunk]`; `query` returns matching chunks as `VectorSearchResult(score=0.9)`, at most `top_k`; has `async close()`.
  - `class FakeReranker` — `async rerank(query, documents) -> [0.9] * len(documents)`; `async close()`.

- [ ] **Step 1: Write failing tests** in `tests/unit/test_config.py`:
  - `test_settings_ignore_dev_env_file` — with `APP_ENV_FILE` pointing at `tests/test.env`, `Settings().MISTRAL_API_KEY == "test-not-a-real-key"`, `LANGFUSE_PUBLIC_KEY == ""`, `EXA_API_KEY == ""`.
  - `test_fake_services_rejected_in_production` — `Settings(ENVIRONMENT="production", EXTERNAL_SERVICES="fake")` raises `ValidationError`.
  - `test_database_uri_uses_scheme_and_query` — `DB_SCHEME="cockroachdb+asyncpg", DB_QUERY="ssl=disable"` gives a URI starting `cockroachdb+asyncpg://` and ending `?ssl=disable`.
  - `test_defaults_unchanged` — `EXTERNAL_SERVICES == "live"`, `DB_POOL_SIZE == 5`, `DB_MAX_OVERFLOW == 10`, URI starts `postgresql+asyncpg://`.
- [ ] **Step 2:** Run `uv run pytest tests/unit/test_config.py -v`. Expected: FAIL (unknown settings).
- [ ] **Step 3:** Write `tests/test.env`: `ENVIRONMENT=local`, `EXTERNAL_SERVICES=fake`, `POSTGRESQL_SERVER=127.0.0.1`, `POSTGRESQL_PORT=55432`, `POSTGRESQL_USERNAME`/`PASSWORD`/`DATABASE=chatbot_test`, `REDIS_URL=redis://127.0.0.1:56379/0`, `JWT_SECRET_KEY=test-only-secret-not-for-production-0123456789`, every provider key `test-not-a-real-key`, `SEARCH_PROVIDER=none`, `SUGGESTIONS_ENABLED=false`, `VECTOR_STORE_PROVIDER=pinecone`, `BUG_REPORT_RATE_LIMIT_SECONDS=3600`, `JIRA_DOMAIN=jira.example.com`, `JIRA_EMAIL=bot@example.com`, `JIRA_PROJECT_KEY=TEST`, `JIRA_ISSUE_TYPE=Bug`, `ADMIN_EMAIL=admin@example.com`, `ADMIN_PASSWORD=AdminPassw0rd!`, `CORS_ORIGINS=[]`.
- [ ] **Step 4:** In `config.py`: read `APP_ENV_FILE` for `env_file`, add the settings above, build the URI from `DB_SCHEME` + `DB_QUERY`, add a `model_validator` rejecting `fake` with `production`.
- [ ] **Step 5:** In `database.py`, pass `pool_size` and `max_overflow` from settings.
- [ ] **Step 6:** Write `services/fakes.py`. In `lifespan.py`, when `settings.EXTERNAL_SERVICES == "fake"`, set `app.state.llm_service`, `embedding_service`, `vector_store_service`, `reranker_service` from the fakes, `search_provider = None`, and skip `init_tracing`. The live branch stays byte-for-byte as it is.
- [ ] **Step 7:** Run the tests. Expected: PASS.
- [ ] **Step 8: Regression check.** With your normal `.env`, start the dev stack (`docker compose --env-file ./backend/app/.env up -d --build backend`) and confirm `GET /health/` is 200 and the startup log still says `vector_store_initialized`.
- [ ] **Step 9: Commit** `feat: config seams for isolated tests and fake external services`.

### Task A3: conftest, fixtures, first green test

**Files:**
- Create: `tests/conftest.py`, `tests/support/__init__.py`, `tests/support/fakes.py`, `tests/support/factories.py`, `tests/support/sse.py`, `tests/integration/test_health.py`, `tests/unit/test_guard.py`

**Interfaces — every later test task consumes these:**

```python
# conftest.py fixtures
app            # session; main.app inside asgi_lifespan.LifespanManager
client         # function; httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
make_client    # function; () -> AsyncClient with its own cookie jar (a second browser)
db             # function; AsyncSession from core.database.SessionLocal
redis          # function; app.state.redis_service.redis_client
settings_override  # function; (**values) -> None, monkeypatches getSettings() attributes
scripted_llm   # function; (turns, completion="Test Title") -> ScriptedLLM installed on app.state.llm_service, restored after
user, admin    # function; (User, headers: dict) logged in through the real /api/auth/login
flush_audit    # function; async () -> None, drains and writes the audit queue

# support/factories.py
DEFAULT_PASSWORD = "Passw0rd!x"
async def create_user(db, *, email=None, password=DEFAULT_PASSWORD, role="users", is_active=True) -> User
async def login(client, email, password=DEFAULT_PASSWORD) -> str            # access token; cookie lands in client's jar
def auth_headers(token: str) -> dict[str, str]
async def create_conversation(db, user_id, title="New Conversation") -> Conversation
async def chat(client, headers, conversation_id, message) -> list[dict]     # POSTs /api/chat, reads to EOF, returns parsed events

# support/sse.py
def parse_sse(body: str) -> list[dict]

# support/fakes.py
class ScriptedLLM(AIPlatform):
    def __init__(self, turns: list[list[TurnChunk] | Exception], completion: str | Exception = "Test Title")
    calls: list[dict]              # kwargs of each stream_turn call, in order
    gate: asyncio.Event | None     # when set to an Event, stream_turn waits on it after the first chunk
```

`ScriptedLLM.stream_turn` pops the next entry of `turns`: an `Exception` is raised, a list is yielded chunk by chunk. Running out of turns raises `AssertionError("unexpected model call")`.

- [ ] **Step 1: Write failing tests.**
  - `tests/unit/test_guard.py`: `test_guard_rejects_non_test_database` (`assert_safe_test_target` with database `chatbot` raises `RuntimeError`), `test_guard_rejects_default_redis_port` (`redis://localhost:6379/0` raises), `test_guard_rejects_live_services` (`EXTERNAL_SERVICES="live"` raises), `test_guard_rejects_remote_host` (`POSTGRESQL_SERVER="db.example.com"` raises), `test_guard_rejects_dev_database` (a dev env file naming the same host, port and database raises, even if that database is called `x_test`), `test_guard_accepts_test_env` (values from `tests/test.env` pass, with and without a dev env file present).
  - `tests/integration/test_health.py`: `test_health_ok` — `GET /health/` → 200 and `{"health": True, "redis": True, "database": True}`; `test_health_redirect` — `GET /health` → 307.
- [ ] **Step 2:** Run. Expected: FAIL (no conftest).
- [ ] **Step 3: Write `conftest.py`.** Order matters (F2):
  1. First lines, before any app import: `os.environ.setdefault("APP_ENV_FILE", str(Path(__file__).parent / "test.env"))`.
  2. Import settings, call `assert_safe_test_target(getSettings())`.
  3. Lower bcrypt cost for speed: `auth.security.gensalt = functools.partial(bcrypt.gensalt, rounds=4)` (tests only; benchmarks keep cost 12).
  4. Session fixture `_schema` (sync): `subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=<backend/app>, check=True)`. A subprocess is needed because `alembic/env.py` calls `asyncio.run`. Then seed roles with `seed.seed_permissions` + `seed.seed_roles`. This also proves the migrations apply to an empty database.
  5. Autouse function fixture `_clean`: discard `app.state.audit_writer._drain()`, then `TRUNCATE audit_logs, llm_usage, pending_jira_tickets, documents, messages, session, conversations, users CASCADE` (roles and permissions survive), then `FLUSHDB`.
- [ ] **Step 4 (D1 — yours): write `assert_safe_test_target(settings, dev_env_file: Path | None = <backend/app/.env>) -> None`** in `conftest.py`. It is the only thing between `TRUNCATE … CASCADE` and whatever database the process is pointed at. "Safe" means a separate Postgres instance that is provably not the dev one. Raise `RuntimeError` naming the failed rule unless all of these hold:
  1. `POSTGRESQL_DATABASE` ends with `_test`.
  2. `POSTGRESQL_SERVER` is `127.0.0.1` or `localhost`.
  3. `EXTERNAL_SERVICES == "fake"`.
  4. The Redis URL's port is not 6379.
  5. If `dev_env_file` exists, the test target's (host, port, database) differs from the one in that file. Read it with `dotenv_values` (already installed with `pydantic-settings`); treat `localhost` and `127.0.0.1` as the same host; never print its values.

  Rule 5 is what makes "another instance" checkable rather than assumed: a name ending in `_test` on the dev server would pass rules 1–4. The CockroachDB test run (Task F1) satisfies the same rules on port 56257.
- [ ] **Step 5:** Write `support/` modules per the interfaces. `create_user` inserts the row and the `users_roles` link directly; `login` posts form fields `username`/`password` to `/api/auth/login`.
- [ ] **Step 6:** Run `uv run pytest tests -v`. Expected: PASS, with no network access (pull the network cable or disable Wi-Fi once to prove it).
- [ ] **Step 7: Commit** `test: conftest, fixtures and health smoke test`.

---

# Phase B — Functional tests (spec §3, priorities 1–10)

Each task: write the listed tests, run them, fix only test code unless a test exposes a defect. A defect listed in Findings gets `@pytest.mark.xfail(reason="F<n>", strict=False)` on the test that states the *desired* behavior, plus a passing test that pins the *current* behavior. Do not change app behavior in this phase. Error bodies have the shape `{"success": false, "error": {"code", "message"}}`.

### Task B1: Unit tests

**Files:** Create `tests/unit/test_security.py`, `test_tokens.py`, `test_context_budget.py`, `test_titles.py`, `test_fallback_llm.py`, `test_suggestions.py`, `test_sse_format.py`, `test_client_info.py`, `test_upload_validation.py`

- [ ] **Step 1: Write tests.**
  - security: hash/verify round-trip; `verify_hash("x", "not-a-hash") is False`; `hash_token` is 64 hex chars and stable.
  - tokens: access payload has `type == "access"`, `sid`, `sub`, `exp - iat == 900`; refresh `exp - iat == 604800`; two tokens for the same inputs differ (`jti`); a tampered token raises `InvalidTokenError`.
  - context budget (`ScriptedLLM`, `settings_override(MAX_REDIS_MESSAGES=4, MIN_RECENT_TURNS=1)`): 4 messages return unchanged with no summarize call; 8 messages return 4 and one summarize call containing the 4 evicted; never fewer than `MIN_RECENT_TURNS * 2`.
  - titles: `is_untitled` true for `None`, `""`, `"New Conversation"`; `fallback_title` keeps at most 6 words; `generate_title` returns the fallback when the model raises, and when it exceeds the timeout.
  - fallback LLM: primary raises before output → fallback's chunks; primary raises after a chunk → the error propagates; `should_fallback` false → propagates; `is_transient_error(httpx2.ConnectError("x")) is True`, `is_transient_error(ValueError()) is False`.
  - suggestions: `parse_suggestions("1. A?\n- a?\nhttp://x.y z\nB question?\nC question?\nD question?")` returns 3 items, deduplicated case-insensitively, no links.
  - SSE format: `sse(DoneEvent()) == 'data: {"type":"done","finishReason":"stop"}\n\n'`.
  - client info: `trusted_client_ip` is `None` by default, and the `X-Real-IP` value with `TRUST_PROXY_HEADERS=True`.
  - upload validation: 0 bytes, over `MAX_UPLOAD_BYTES`, and `evil.exe` with `application/octet-stream` each raise `ValidationError`; `notes.txt` passes.
- [ ] **Step 2:** `uv run pytest tests/unit -v`. Expected: PASS.
- [ ] **Step 3: Commit** `test: unit tests`.

### Task B2: Authentication (priority 1)

**Files:** Create `tests/integration/test_auth.py`

- [ ] **Step 1: Write tests.**
  - register: 201 `{id, email}`; duplicate 409 `CONFLICT`; 7-char password 422; `ALLOW_PUBLIC_REGISTRATION=False` → 403.
  - login: 200 `{access_token, token_type: "bearer"}`; `Set-Cookie` `refresh_token` is `HttpOnly`, `Path=/api/auth`, `SameSite=lax`; wrong password and unknown email both 401 with the same message `Incorrect email or password`; inactive user 401.
  - `/api/auth/me`: returns `permissions` sorted; no token 401.
  - refresh: 200, new access token, cookie value changes; no cookie 401 `Refresh token is required`; an access token in the cookie 401.
  - token reuse inside grace: old cookie replayed within 30 s → 409, session row still present.
  - token reuse outside grace (`REFRESH_REUSE_GRACE_SECONDS=0`): old cookie → 401, session row deleted, and the *new* token is now 401 too.
  - logout: 200, cookie cleared, session row gone, the old access token → 401 on `/me`.
  - `/api/auth/clear-session` with no access token: 200, session row gone.
- [ ] **Step 2:** `uv run pytest tests/integration/test_auth.py -v`. Expected: PASS.
- [ ] **Step 3: Commit** `test: authentication`.

### Task B3: Sessions and permissions (priorities 2–3)

**Files:** Create `tests/integration/test_sessions.py`, `tests/integration/test_permissions.py`

- [ ] **Step 1: Write session tests.**
  - expiry: set `session.expires_at` to the past → `/me` 401, refresh 401 `Refresh token has expired`, row deleted. Same for `absolute_expires_at`.
  - multiple sessions: two clients log in → 2 rows; logging one out leaves the other working.
  - cap: 6 sequential logins with `MAX_REFRESH_SESSIONS_PER_USER=5` → 5 rows, the first login's access token → 401.
  - admin revocation: `DELETE /api/admin/sessions/{id}` → that user's token 401; `POST /api/admin/users/{id}/revoke-sessions` → all of that user's tokens 401.
  - ban: `POST /api/admin/users/{id}/ban` → the user's next request is rejected and login is 401; `/unban` restores login.
- [ ] **Step 2: Write permission tests.**
  - parametrized over every protected route: no token → 401.
  - parametrized over the 12 `/api/admin/*` routes: a `users`-role token → 403 `FORBIDDEN`.
  - admin token → 200 on `GET /api/admin/users`, `/pending-tickets`, `/summary`, `/audit-logs`, `/usage`.
  - a user with no role → 403 on `GET /api/conversations`.
  - live permissions: delete the user's `users_roles` row → the same access token gets 403 on the next request.
  - audit attribution: after `flush_audit()`, a 403 has an `audit_logs` row with that `user_id` and `status_code == 403`.
- [ ] **Step 3:** Run both files. Expected: PASS.
- [ ] **Step 4: Commit** `test: sessions and permissions`.

### Task B4: Conversations and database (priorities 4–5)

**Files:** Create `tests/integration/test_conversations.py`, `tests/integration/test_database.py`

- [ ] **Step 1: Write conversation tests.** Create → 201, title `New Conversation`; 101-char title → 422; list returns only the caller's, newest first; another user's conversation → 404 `NOT_FOUND` on get and on `/messages`; malformed id → 422.
- [ ] **Step 2: Write database tests.**
  - cascade: `DELETE FROM users WHERE id = …` removes that user's conversations, messages, sessions, documents.
  - `SET NULL`: deleting a conversation keeps its `llm_usage` rows with `conversation_id IS NULL`; deleting a user keeps `audit_logs` rows with `user_id IS NULL`.
  - unique email raises `IntegrityError`.
  - `save_turn` is atomic: with a non-existent `conversation_id` it returns `False` and leaves 0 rows.
  - ids are time-ordered: two inserts in a row give `second.id > first.id` (this test is expected to matter in F1).
  - `messages.parts` round-trips a nested list of dicts unchanged.
- [ ] **Step 3:** Run. Expected: PASS.
- [ ] **Step 4: Commit** `test: conversations and database`.

### Task B5: Redis memory and rate limiting (priorities 6–7)

**Files:** Create `tests/integration/test_redis_memory.py`, `tests/integration/test_rate_limits.py`

- [ ] **Step 1: Write Redis tests.**
  - cache hit: after `set_conversation_state`, `get_conversation_state(db=None)` returns the same messages.
  - cold cache: with rows only in Postgres, `get_conversation_state(db=db, llm=ScriptedLLM([]))` returns them and `LLEN chat:user:{u}:conversation:{c}` equals the row count.
  - TTL: `0 < TTL(history key) <= 86400`; the summary key's TTL is refreshed by a later write.
  - `replace_history([])` deletes the key.
  - Redis unreachable (client built on `redis://127.0.0.1:1`): `get_history` returns `[]`, `get_summary` returns `None`, `consume_daily_quota` returns `False`, and `set_conversation_state` returns `True` — the last one pins F12.
- [ ] **Step 2: Write rate-limit tests.**
  - chat quota (`CHAT_DAILY_LIMIT_PER_USER=2`): third `POST /api/chat` → 429 `TOO_MANY_REQUESTS`, message contains `limit of 2 messages`; `ScriptedLLM.calls` has length 2; key `quota:chat:{user}:{UTC date}` has `0 < TTL <= 172800`. Limit `0` allows a third.
  - login failures (`LOGIN_MAX_FAILURES_PER_ACCOUNT=3`): the fourth attempt is 429 even with the right password; a success before the cap clears the counter.
  - registration (`REGISTRATION_MAX_GLOBAL=2`): third → 429 `Sign-ups are paused…`. Per-IP cap applies only with `TRUST_PROXY_HEADERS=True` and an `X-Real-IP` header.
  - `try_acquire_rate_limit` twice → `True`, `False`; after `release_rate_limit` → `True`.
- [ ] **Step 3:** Run. Expected: PASS.
- [ ] **Step 4: Commit** `test: redis memory and rate limits`.

### Task B6: SSE and agent (priorities 8–9)

**Files:** Create `tests/agent/test_sse_stream.py`, `tests/agent/test_agent_tools.py`

All tests post to `/api/chat` with `ScriptedLLM` and read the stream to the end. Open-Meteo and Exa are mocked with respx.

- [ ] **Step 1: Write SSE tests.**
  - plain reply: events are `text-delta`+ then `done` last; joined deltas equal the stored model message.
  - headers: `content-type` starts `text/event-stream`, `x-accel-buffering: no`.
  - title: first turn of a `New Conversation` emits `title` before `done` and updates the row; the second turn emits none.
  - suggestions (`SUGGESTIONS_ENABLED=True`, completion `"A question?\nB question?\nC question?"`): a `suggestions` event with 3 items before `done`, and a `suggestions` part on the stored message.
  - model error: `turns=[RuntimeError("boom")]` → exactly one `error` with code `STREAM_GENERATION_FAILED`, no `done`.
  - turn timeout (`AGENT_TURN_TIMEOUT_SECONDS=0.1`, `gate` never set) → `error` with code `TURN_TIMEOUT`.
  - validation: empty message and an 8001-character message → 422 JSON, not a stream.
- [ ] **Step 2: Write agent tests.**
  - tool selection: `turns=[["Let me check.", [ToolCall("c1", "get_weather", {"city": "Paris"})]], ["Sunny."]]` → event types in order `text-delta, text-delta, tool-start, tool-result, text-delta, done`; `tool-start` has `toolName == "get_weather"`, `toolCallId == "c1"`; `tool-result.isError is False`; the second `calls` entry has one exchange whose result contains `Paris`.
  - tool failure recovery: geocoding returns 500 → `tool-result.isError is True` and the stream still ends with `done`.
  - unknown tool name → `isError True`, then `done`.
  - tool timeout (`TOOL_TIMEOUT_SECONDS=0.05`, respx side effect sleeps 0.5 s) → `isError True`.
  - round cap (`AGENT_MAX_TOOL_ROUNDS=1`): the second `stream_turn` call has `allow_tools is False`.
  - per-round cap (`AGENT_MAX_CALLS_PER_ROUND=1`, two calls): second `tool-result.isError is True`.
  - offered tools: with `SEARCH_PROVIDER=none` and no documents, tool names passed to the model are exactly `{"get_weather", "report_bug"}`.
  - `report_bug`: creates one `pending_jira_tickets` row; a second call in the window → `isError True`, still one row.
  - fallback model: `app.state.llm_service = FallbackLLM(primary=ScriptedLLM([RuntimeError()]), fallback=ScriptedLLM([["from fallback"]]), should_fallback=lambda e: True)` → stored reply is `from fallback`.
- [ ] **Step 3:** `uv run pytest tests/agent -v`. Expected: PASS.
- [ ] **Step 4: Commit** `test: sse stream and agent loop`.

### Task B7: Documents (priority 10)

**Files:** Create `tests/integration/test_documents.py`

- [ ] **Step 1: Write tests.**
  - upload `notes.txt` → 202 with `status == "processing"`; a following `GET …/documents` shows `status == "indexed"`, `chunkCount >= 1`; `FakeVectorStore` holds chunks for that document; the temp file no longer exists.
  - rejects: empty file, `.exe`, and an oversized file (`MAX_UPLOAD_BYTES=10`) → 422; another user's conversation → 404.
  - indexing failure: patch `app.state.embedding_service.embed_texts` to raise → `status == "failed"`, `errorMessage` set.
  - delete → 204, row gone, the store has no chunks for it; another user's document → 404.
  - retrieval: with an indexed document, a chat whose script calls `search_documents` emits a `sources` event before `done` with `number == 1`, and the stored message has a `sources` part.
- [ ] **Step 2:** Run. Expected: PASS.
- [ ] **Step 3: Commit** `test: documents`.

---

# Phase C — Chatbot lifecycle (spec §4)

### Task C1: End-to-end happy path

**Files:** Create `tests/integration/test_chat_lifecycle.py`

- [ ] **Step 1: Write `test_chat_lifecycle_end_to_end`** — one test, two turns, asserting each numbered point of §4:
  1. `user` posts `{"message": "hello", "conversationId": …}` → 200 stream.
  2. the log-free proof of authorization: the same request with another user's token → 404 (asserted first, and `quota:chat:*` for that user does not exist afterwards).
  3. turn 1 runs on a cold cache: `scripted.calls[0]["history"] == []`.
  4. the scripted reply `["Hi ", "there"]` is what was streamed.
  5. event types are exactly `["text-delta", "text-delta", "title", "done"]`.
  6. `messages` has 2 rows in order `user`/`model` with contents `hello` / `Hi there`; `llm_usage` rows are zero (the fake records none) and the conversation title is `Test Title`.
  7. Redis `LLEN` of the history key is 2.
  - Then `DEL` the history key and send turn 2: `scripted.calls[1]["history"]` has 2 entries (rebuilt from Postgres), and afterwards `LLEN == 4` and `messages` has 4 rows.
- [ ] **Step 2:** Run. Expected: PASS.
- [ ] **Step 3: Commit** `test: chat lifecycle end to end`.

### Task C2: Failure scenarios

**Files:** Create `tests/integration/test_chat_failures.py`, `tests/support/server.py`

**Interfaces:**
- Produces fixture `live_server` → base URL of the same `app` served by `uvicorn.Server` on a free port inside the session loop. Needed because `httpx.ASGITransport` buffers the whole response, so it cannot drop a connection mid-stream.

- [ ] **Step 1: Write tests.**
  - agent failure: `error` event, 0 message rows, no history key, and the quota key equals `1` (the failed turn still counted — pin it).
  - Redis unavailable, default limit: swap `redis_client` for one on `127.0.0.1:1` → `POST /api/chat` is 429 (F12; this pins today's behavior and Task X2 flips it); `GET /health/` is 503 with `"redis": false`.
  - Redis unavailable, `CHAT_DAILY_LIMIT_PER_USER=0`: the stream completes with `done` and both messages are in Postgres.
  - database persistence failure: patch `services.streaming.save_postgres_turn` to return `False` → the client still received `done`, Redis has the turn, Postgres has 0 rows (F11). Patched to raise → events end `…, done, error` (F10).
  - invalid access: unknown conversation id → 404; no token → 401; a user without `ai:chat` → 403. None of them creates a quota key.
  - `test_interrupted_stream` (uses `live_server`): `ScriptedLLM` with `gate = asyncio.Event()`; open the stream with `client.stream(...)`, read the first event, close the response, then `gate.set()`. Within 2 s: 0 message rows, no history key, and a following `GET /health/` is 200.
  - `test_disconnect_after_done_loses_turn` (uses `live_server`, Review Focus 3): close the response on receiving `done` → assert the number of message rows is 0 **or** 2 and record which in the test's docstring after the first run. If 0, it is a real data-loss path for impatient clients; add it to `docs/multi-instance.md` as a known issue.
- [ ] **Step 2:** Run. Expected: PASS.
- [ ] **Step 3: Commit** `test: chat failure scenarios`.

---

# Phase D — Concurrency (spec §3, §8 data consistency)

### Task D1: Race tests

**Files:** Create `tests/concurrency/test_auth_races.py`, `tests/concurrency/test_chat_races.py`, `tests/concurrency/test_resource_races.py`

All use `asyncio.gather` over separate `make_client()` instances against real Postgres and Redis. Tests asserting desired behavior on a known finding are `xfail`; the rest are strict.

- [ ] **Step 1: Write auth races.**
  - 20 concurrent registrations of one email → exactly one 201, exactly one `users` row, the rest in `{409, 500}`. `xfail(F16)`: none is 500.
  - 10 concurrent refreshes with one cookie → exactly one 200, the rest 409, one session row, and the winner's new cookie works.
  - 10 concurrent logins with `MAX_REFRESH_SESSIONS_PER_USER=5` → all 200. `xfail(F15)`: at most 5 session rows.
- [ ] **Step 2: Write chat races.**
  - quota: `CHAT_DAILY_LIMIT_PER_USER=5`, 20 concurrent chats → exactly 5 streams and 15 429s, 10 message rows.
  - 10 concurrent turns in one conversation → 20 message rows (nothing lost in Postgres). `xfail(F14)`: Redis `LLEN == 20`.
  - 20 users each chatting once, concurrently → every conversation has exactly its own 2 messages and each reply starts with that user's scripted text (no cross-talk).
  - 5 concurrent `report_bug` calls by one user → 1 ticket.
- [ ] **Step 3: Write resource races.**
  - 50 concurrent `POST /api/conversations` → 50 distinct ids, 50 rows.
  - 50 concurrent `GET /api/conversations` with the default pool (15 connections) → all 200.
  - two admins approve one ticket concurrently (Jira mocked with respx) → the Jira route was called exactly once and one response is a success. This is the "no duplicate downstream operation" check.
- [ ] **Step 4:** `uv run pytest tests/concurrency -v`, three times in a row. Expected: same result each time (PASS with the xfails listed above). A test that flips between runs is a real race; record it in Findings instead of loosening it.
- [ ] **Step 5:** Run the full required command `uv run pytest tests -v --cov=. --cov-report=term-missing`. Record the coverage total in `docs/testing.md`.
- [ ] **Step 6: Commit** `test: concurrency tests`.

---

# Phase X — Decided behavior changes (after D, before E)

The suite from Phases A–D is the safety net here. Each task follows the same loop: change the tests to state the new behavior, watch them fail, change the app, watch them pass, then run the whole suite.

### Task X1: Argon2id password hashing

**Files:**
- Modify: `backend/app/pyproject.toml` (`uv add argon2-cffi`; keep `bcrypt` for old hashes), `core/config.py`, `auth/security.py`, `auth/service.py:26-34`, `services/user.py:34`, `tests/test.env`, `tests/conftest.py`, `tests/unit/test_security.py`, `tests/integration/test_auth.py`
- `seed.py:114` keeps calling the sync `get_hash` (it runs outside the server).

**Interfaces:**
- Settings: `ARGON2_MEMORY_KIB: int = 19456`, `ARGON2_TIME_COST: int = 2`, `ARGON2_PARALLELISM: int = 1` (OWASP's minimum Argon2id profile), `PASSWORD_HASH_CONCURRENCY: int = 4`.
- `auth/security.py`:
  - `get_hash(text: str) -> str` — Argon2id, synchronous.
  - `verify_hash(plain_text: str, hashed_text: str) -> bool` — a hash starting `$2` is checked with bcrypt, one starting `$argon2` with Argon2; anything else is `False`.
  - `needs_rehash(hashed_text: str) -> bool` — `True` for bcrypt hashes and for Argon2 hashes made with weaker parameters.
  - `async hash_password(text: str) -> str` and `async verify_password(plain_text: str, hashed_text: str) -> bool` — run the sync functions in the threadpool behind an `asyncio.Semaphore(PASSWORD_HASH_CONCURRENCY)` created on first use.

**Why the semaphore:** Argon2 uses memory on purpose. Four hashes at once is 4 × 19 MiB ≈ 76 MiB; an unbounded threadpool (40 threads) would be ≈ 760 MiB, more than the 512 MB container limit in Phase E.

**What this does and does not fix:** hashing moves off the event loop, so a login no longer stalls other requests on the instance. Hashing is still CPU work, so logins per second per instance stay bounded by cores ÷ hash time. Expect the auth workload to scale with instances.

- [ ] **Step 1: Write failing tests.**
  - `get_hash("x")` starts with `$argon2id$`; round-trip verifies; a wrong password is `False`.
  - a bcrypt hash made in the test with `bcrypt.hashpw` verifies with `verify_hash`; `needs_rehash` is `True` for it and `False` for a fresh Argon2 hash.
  - `verify_hash("x", "garbage") is False`.
  - `hash_password` runs outside the event-loop thread (patch `get_hash` to record `threading.get_ident()` and compare with the test's).
  - login upgrade: a user row holding a bcrypt hash logs in → 200, and the stored hash now starts `$argon2id$`; the second login is 200.
  - a wrong password for that user → 401 and the stored hash is unchanged.
  - unknown email still returns 401 `Incorrect email or password`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. In `authenticate_user`, use `verify_password`, and after a successful check call `needs_rehash`; if true, store `await hash_password(password)` in the same session before the login commits. `_DUMMY_PASSWORD_HASH` becomes an Argon2 hash. `create_user_service` uses `hash_password`.
- [ ] **Step 4:** In `tests/test.env` set `ARGON2_MEMORY_KIB=64`, `ARGON2_TIME_COST=1`. Remove the `gensalt` patch from `conftest.py` (Task A3 Step 3, item 3).
- [ ] **Step 5:** Run `uv run pytest tests -v`. Expected: PASS.
- [ ] **Step 6: Commit** `feat: argon2id password hashing with bcrypt upgrade on login`.

Known and accepted: until an old account logs in again, its hash stays bcrypt, and its login takes a slightly different time than an Argon2 one.

### Task X2: Chat keeps working when Redis is down (D2)

**Files:**
- Modify: `services/memory.py:13-18,58-74`, `api/routes/streamchat.py:55-63`, `tests/integration/test_chat_failures.py`, `tests/integration/test_redis_memory.py`

**Interfaces:**
- `RedisMemoryService.__init__` builds the client with `socket_connect_timeout=1.0, socket_timeout=2.0` (F27).
- `consume_daily_quota(user_id, action, limit, *, fail_open: bool = False) -> bool` — on a Redis error returns `fail_open`. The chat route passes `fail_open=True`; `_web_search` keeps the default, because that quota guards a paid API.

- [ ] **Step 1: Change the tests.**
  - Redis unavailable, default limit: `POST /api/chat` → 200, the stream ends with `done`, both messages are in Postgres, and the whole request takes under 10 s.
  - second turn during the outage: `scripted.calls[1]["history"]` has 2 entries (read from Postgres).
  - `consume_daily_quota(..., fail_open=True)` is `True` and `consume_daily_quota(...)` is `False` on an unreachable client.
  - with Redis reachable the quota is still enforced (the Task B5 test is untouched and still passes).
  - `test_history_not_stale_after_outage`, marked `xfail(reason="F28")`: seed Redis with 2 messages, break the client, chat once, restore the client, chat again → desired `history` length 4, actual 2. Redis still holds the pre-outage list, so the model misses the turns saved only to Postgres. Add F28 to Findings and to `docs/multi-instance.md`; the fix (compare against Postgres before trusting the cache) is a follow-up, not part of this plan.
- [ ] **Step 2:** Run. Expected: FAIL on the first three.
- [ ] **Step 3:** Implement. Log a warning event `chat.quota.check.skipped` when the quota is skipped.
- [ ] **Step 4:** Run `uv run pytest tests -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: chat stays available during a redis outage`.

Startup is unchanged: the app still refuses to start without Redis (`lifespan.py:53`).

### Task X3: `Idempotency-Key` header (D4)

**Files:**
- Create: `core/idempotency.py`, `alembic/versions/<rev>_add_idempotency_keys.py` (`down_revision` = the output of `uv run alembic heads`), `tests/integration/test_idempotency.py`
- Modify: `schemas/models.py`, `services/conversation.py`, `api/routes/conversations.py`, `services/message.py`, `services/streaming.py`, `services/graph/runner.py`, `api/routes/streamchat.py`, `services/memory.py`

**Interfaces:**
- `core/idempotency.py`: `def idempotency_key(value: str | None = Header(default=None, alias="Idempotency-Key", min_length=1, max_length=128)) -> str | None`
- Columns: `conversations.idempotency_key` and `messages.idempotency_key`, both `String(128)`, nullable. Unique indexes `uq_conversations_user_idem (user_id, idempotency_key)` and `uq_messages_conversation_idem (conversation_id, idempotency_key)`. Null keys never collide, so existing rows are unaffected.
- `create_conversation(db, user_id, title="New Conversation", idempotency_key=None) -> Conversation` — on a unique violation, roll back and return the existing row.
- `save_turn(..., idempotency_key=None) -> bool` — stores the key on the user message.
- `async get_turn_by_key(db, conversation_id, key) -> tuple[Message, Message] | None` — the user message with that key and the model message right after it.
- `RedisMemoryService.acquire_inflight(key: str, ttl_seconds: int) -> bool | None` (`SET NX EX`; `None` on a Redis error) and `release_inflight(key: str) -> None`.

**Behavior (the guarantee is the Postgres unique index; Redis only saves a wasted model call):**
- No header: exactly as today.
- `POST /api/conversations` with a key: the first call creates; a repeat by the same user returns 201 with the same conversation.
- `POST /api/chat` with a key, in this order after the ownership check:
  1. The key already has a saved turn → replay it as a stream: one `text-delta` with the stored text, then `sources` and `suggestions` if the stored parts have them, then `done`. No model call, no quota use, no writes.
  2. `acquire_inflight("idem:chat:{conversation_id}:{key}", AGENT_TURN_TIMEOUT_SECONDS + 30)` is `False` → 409 `CONFLICT`, `This message is already being processed.` `None` (Redis down) → carry on.
  3. Run the turn normally; release the lock when the stream ends.
- The same key with a different message body is not detected; the stored result is replayed. Documented, not enforced.

- [ ] **Step 1: Write failing tests.**
  - conversation: two posts with one key → same `id`, 1 row; the same key from another user → a different conversation; no key twice → 2 rows.
  - chat replay: the same key twice → 2 message rows, `len(scripted.calls) == 1`, the second stream's joined text equals the first, the quota key equals `1`.
  - chat in flight: with `gate` holding the first request open, a second with the same key → 409; after `gate.set()` the first completes.
  - Redis down: the same key twice in sequence → still 2 message rows (the index holds).
  - 10 concurrent chats with one key → exactly 2 message rows; every response is a 200 stream or a 409.
  - a 129-character key → 422; an empty header → 422.
  - migration: `alembic downgrade -1` then `upgrade head` runs clean on the test database.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement the migration, models, services and routes.
- [ ] **Step 4:** Run `uv run pytest tests -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: optional Idempotency-Key on chat and conversation creation`.

Not in scope: the frontend sending a key. That is a one-line header in `frontend/Chatbot/lib/api/chatApi.ts:32` whenever you want browser retries covered.

### Task X4: Switchable id strategy (D5)

**Files:**
- Create: `core/ids.py`, `alembic/versions/<rev>_id_default_follows_strategy.py`, `tests/integration/test_id_strategy.py`
- Modify: `core/config.py`, `schemas/models.py` (10 id columns), the 8 migrations that contain `uuidv7()` (`6090023d1049`, `9db8d2a36591`, `a1b2c3d4e5f6`, `a7b8c9d0e1f2`, `af7d28136461`, `b7c8d9e0f1a2`, `c4cd36485924`, `c9d0e1f2a3b4`), `api/routes/admin_audit.py:75-83`, `api/routes/admin_users.py:62-66,107`, `services/message.py`, `tests/integration/test_database.py`

**Interfaces:**
- Setting `ID_STRATEGY: Literal["uuidv7", "random"] = "uuidv7"`.
- `core/ids.py`: `ID_DEFAULT_SQL = {"uuidv7": "uuidv7()", "random": "gen_random_uuid()"}` and `def id_server_default() -> TextClause`.
- Models and the 8 old migrations use `server_default=id_server_default()` in place of `text("uuidv7()")`. With the default strategy the generated SQL is identical to today's, so production and existing databases see no difference; with `random` a fresh database gets `gen_random_uuid()`, which both Postgres 18 and CockroachDB have.
- New migration, for a database that already exists: `upgrade` runs `ALTER TABLE … ALTER COLUMN id SET DEFAULT <current strategy's SQL>` on all 10 tables; `downgrade` sets `uuidv7()`. A no-op on production. To switch your local Postgres: `uv run alembic downgrade -1`, set `ID_STRATEGY=random`, `uv run alembic upgrade head`. Existing rows keep their ids.

**Ordering must stop depending on ids (F25, F26):**
- `save_turn` sets `created_at` explicitly: the user message at `now`, the model message at `now + 1 microsecond`. `list_messages` orders by `created_at, id`.
- Audit-log and user pagination keep the `cursor: UUID` parameter. The handler looks up that row's `created_at`, filters with `tuple_(created_at, id) < (cursor_created_at, cursor)`, and orders by `created_at DESC, id DESC`. An unknown cursor id → 400 `BAD_REQUEST`. The session list orders by `created_at DESC, id DESC`.

- [ ] **Step 1: Write failing tests** (each must pass under both strategies).
  - 20 chat turns → `GET …/messages` alternates `user`, `model` and matches send order.
  - 25 audit rows with distinct `created_at`, paged at `limit=10` → 3 pages, every row exactly once, newest first. Same for `GET /api/admin/users`.
  - unknown cursor → 400.
  - replace the Task B4 ordering test: under `uuidv7`, `second.id > first.id`; under `random`, `first.id.version == 4`.
  - `id_server_default()` renders `uuidv7()` by default and `gen_random_uuid()` with `ID_STRATEGY=random`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the suite under the default strategy: `uv run pytest tests -v`. Expected: PASS.
- [ ] **Step 5:** Run it under random ids on a fresh database (the test Postgres is on tmpfs, so a restart empties it):
  `docker compose -f docker-compose.test.yml restart db-test`, then in PowerShell `$env:ID_STRATEGY="random"; uv run pytest tests -v; Remove-Item Env:ID_STRATEGY`. Expected: PASS.
- [ ] **Step 6:** Confirm no drift for production: on a database migrated before this task, `uv run alembic upgrade head` succeeds and `\d users` still shows `DEFAULT uuidv7()`.
- [ ] **Step 7: Commit** `feat: switchable id strategy and id-independent ordering`.

---

# Phase E — k6 and the Phase 1 baseline (spec §6, §7 Phase 1)

### Task E1: Phase 1 bench stack and dataset

**Files:**
- Create: `infra/bench/bench.env`, `infra/bench/compose.phase1.yml`, `infra/bench/nginx/phase1.conf`, `backend/app/scripts/bench_seed.py`
- Modify: `backend/Dockerfile` (add `ARG UV_EXTRA_ARGS=""` and append it to both `uv sync` lines; default build is unchanged)

**Interfaces:**
- Produces: compose project `chatbot-bench-p1`; `http://127.0.0.1:58080` (nginx) and `:58001` (api1 direct).
- Produces dataset: users `bench0@example.com` … `bench199@example.com`, password `BenchPassw0rd!`, role `users`, each with 5 conversations of 20 messages.
- Produces limits, identical in every phase: api 1.0 CPU / 512 MB each; nginx 0.5 / 128 MB; redis 0.5 / 256 MB; postgres 2.0 / 1 GB.

- [ ] **Step 1:** Write `bench.env`: as `tests/test.env` but `POSTGRESQL_SERVER=db`, `POSTGRESQL_PORT=5432`, database/user/password `chatbot_bench`, `REDIS_URL=redis://redis:6379/0`, `DB_POOL_SIZE=10`, `DB_MAX_OVERFLOW=10`, `CHAT_DAILY_LIMIT_PER_USER=0`, `REGISTRATION_MAX_GLOBAL=1000000`, `FAKE_LLM_TOKEN_COUNT=40`, `FAKE_LLM_TOKEN_DELAY_MS=20`, `SUGGESTIONS_ENABLED=false`, `TRUST_PROXY_HEADERS=false` (F9), `ID_STRATEGY=random` (D5). Leave the Argon2 settings out so the production defaults apply. `ENVIRONMENT=local` so the refresh cookie works over plain HTTP.
- [ ] **Step 2:** Write `compose.phase1.yml` (`name: chatbot-bench-p1`): `db` (`postgres:18-alpine`, `command: postgres -c shared_preload_libraries=pg_stat_statements`), `redis`, `migrate`, `seed` (runs `seed.py` then `scripts/bench_seed.py`), `api1` (env `APP_ENV_FILE=/run/bench.env`, healthcheck on `/health/`), `nginx`. Limits via `cpus:` and `mem_limit:`.
- [ ] **Step 3:** Write `nginx/phase1.conf`: `upstream api { server api1:8000 max_fails=2 fail_timeout=5s; keepalive 64; }`; in `location /`: `proxy_http_version 1.1`, `proxy_set_header Connection ""`, `proxy_set_header X-Real-IP $remote_addr`, `proxy_buffering off`, `proxy_read_timeout 300s`, `proxy_next_upstream error timeout http_502 http_504`, `add_header X-Upstream $upstream_addr always`; access log format including `$upstream_addr $status $request_time`. 503 is left out on purpose: `/health/` answers 503 while Redis is down, and counting that as a failed upstream would eject every instance even though chat still works (Task X2). nginx does not replay a `POST` it already sent, which is the safe default given F13.
- [ ] **Step 4:** Write `scripts/bench_seed.py` with `async def seed_bench(users: int = 200, conversations: int = 5, messages: int = 20) -> dict` returning the row counts. Hash the password once with `get_hash` and reuse it for all users (production Argon2 parameters). Give each seeded turn's two messages distinct `created_at` values, as `save_turn` does after Task X4. Idempotent: returns existing counts if `bench0@example.com` exists.
- [ ] **Step 5: Verify.** `docker compose -f infra/bench/compose.phase1.yml up -d --build --wait`; `curl -i http://127.0.0.1:58080/health/` is 200 with an `X-Upstream` header; the seed log prints `{"users": 200, "conversations": 1000, "messages": 20000}`.
- [ ] **Step 6: Commit** `bench: phase 1 stack and synthetic dataset`.

### Task E2: k6 library, health and auth workloads

**Files:** Create `tests/load/lib/config.js`, `tests/load/lib/auth.js`, `tests/load/lib/summary.js`, `tests/load/health.js`, `tests/load/auth.js`

**Interfaces:**
- `lib/config.js`: `BASE_URL` (env, default `http://127.0.0.1:58080`), `options(workload)` returning scenarios for env `PROFILE`:
  - `smoke` — 2 VUs, 30 s.
  - `ramp` (closed model, finds capacity) — scenario `warmup`: 5 VUs for 30 s; scenario `main` starting at 30 s: hold 10, 25, 50, 100 VUs for 90 s each with 15 s ramps.
  - `rate` (open model, latency at a fixed load) — `warmup` as above; `main`: `constant-arrival-rate` at env `RATE` requests/s for 3 min, `preAllocatedVUs: 200`, `maxVUs: 500`.
  - `summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "p(99)", "max"]`, and a threshold on every reported metric tagged `{scenario:main}` so k6 emits those sub-metrics (warm-up is excluded from results).
- `lib/auth.js`: `session()` → `{headers}` for user `bench${(__VU - 1) % 200}@example.com`, logging in once per VU and again when the token is older than 10 minutes (Review Focus 4).
- `lib/summary.js`: `handleSummary(data)` writing `${RESULTS_DIR}/summary.json` with: `total_requests`, `rps`, `rpm` (`rps * 60`), `vus_max`, `avg_ms`, `p50_ms`, `p95_ms`, `p99_ms`, `error_rate`, `timeout_rate`, `dropped_iterations`, `checks_rate`. `timeout_rate` is a custom `Rate` fed by `res.error_code === 1050`.

  VUs, RPS and RPM are reported as three separate fields: `ramp` fixes VUs and measures RPS; `rate` fixes RPS and measures latency and `dropped_iterations`.

- [ ] **Step 1:** Write the three library files.
- [ ] **Step 2:** `health.js` — two endpoint groups, tagged: `GET /health/` (touches Postgres and Redis) and `GET /api/auth/me` (auth + two reads). No think time.
- [ ] **Step 3:** `auth.js` — tagged steps: `login` (form post), `me`, `refresh`, `logout`. This workload is the "transaction-heavy" one: login prunes and inserts a session, refresh takes a row lock. Expect `login` to be bounded by Argon2 CPU time and by `PASSWORD_HASH_CONCURRENCY` (Task X1), while `me` and `refresh` stay fast alongside it.
- [ ] **Step 4: Verify.** `k6 run -e PROFILE=smoke -e RESULTS_DIR=. tests/load/health.js` and the same for `auth.js`: `checks` 100 %, `http_req_failed` 0 %, and a `summary.json` with all 12 fields. Run `auth.js` smoke with the token age threshold temporarily set to 5 s and confirm a second `login` appears.
- [ ] **Step 5: Commit** `bench: k6 library, health and auth workloads`.

### Task E3: Database, conversation and chatbot workloads

**Files:** Create `tests/load/database.js`, `tests/load/conversations.js`, `tests/load/chatbot.js`

- [ ] **Step 1:** `database.js` — env `MIX` selects the workload so each is benchmarked on its own: `read` (100 % `GET /api/conversations` and `GET …/messages`), `write` (100 % `POST /api/conversations`), `mixed` (80/20). No think time.
- [ ] **Step 2:** `conversations.js` — the realistic journey with 1–3 s think time (`randomSeed(42)`): list conversations → open one → read its messages → 1 in 10 creates a conversation.
- [ ] **Step 3:** `chatbot.js` — each iteration creates nothing new: it posts to one of the VU's seeded conversations. Custom metrics: `chat_ttfb` (`res.timings.waiting`), `chat_duration`, `chat_incomplete` (`Rate`, true when the body lacks `"type":"done"`). Timeout 60 s. k6 reads the whole body, which is what persistence needs (F10). With `FAKE_LLM_TOKEN_COUNT=40` and 20 ms per token a reply takes about 0.8 s, so concurrent open streams ≈ RPS × 0.8.
  - Env `CHAT_MODE=live` is a separate benchmark against real Mistral: fixed 1 VU, 10 iterations, results under `bench/results/live/`, never part of the phase comparison. It requires a stack started with `EXTERNAL_SERVICES=live` and real keys, and costs money; the script aborts unless `CONFIRM_PAID_CALLS=yes`.
- [ ] **Step 4: Verify.** Smoke-run each script (and each `MIX`): checks 100 %, `chat_incomplete` 0 %.
- [ ] **Step 5: Commit** `bench: database, conversations and chatbot workloads`.

### Task E4: Runner, resource metrics, Phase 1 results

**Files:** Create `infra/bench/run_bench.py`, `tests/load/rates.json`, `bench/results/phase1/…`

**Interfaces:**
- `python infra/bench/run_bench.py --phase {phase1,phase2,phase3} --workload {health,auth,database-read,database-write,database-mixed,conversations,chatbot} --profile {smoke,ramp,rate} [--rate N] [--label TEXT] [--env KEY=VALUE ...]` (`--env` overrides a `bench.env` value for that run and is recorded in `meta.json`)
- Output directory `bench/results/<phase>/<workload>-<profile>[-<label>]/<UTC timestamp>/` containing:
  - `summary.json` (from k6), `raw.csv.gz` (`k6 --out csv=`, git-ignored)
  - `stats.csv` — `docker stats` sampled every 2 s: timestamp, container, CPU %, memory MiB
  - `db.json` — Postgres: `pg_stat_database` and connection count before/after, top 20 `pg_stat_statements` by total time with `mean_exec_time`. CockroachDB (from Phase F): `sql.conns`, `sql.service.latency-p99`, `txn.restarts`, `ranges.underreplicated` from `crdb_internal.node_metrics`.
  - `redis.json` — `INFO` before/after: `used_memory`, `used_cpu_sys`, `used_cpu_user`, `instantaneous_ops_per_sec`, `commandstats` (`usec_per_call`)
  - `meta.json` — git SHA, dirty flag, k6 version, image ids, compose file hash, container limits, `docker info` NCPU and memory, profile, rate, seed row counts, start/end time

- [ ] **Step 1:** Write `run_bench.py`. Before every run it does `down -v` then `up -d --build --wait` on the phase's compose file, so each run starts from the same seeded dataset and an empty Redis. It refuses to run unless `BASE_URL`'s host is `127.0.0.1` or `localhost`.
- [ ] **Step 2: Test the runner** with `--workload health --profile smoke`: all six files exist and `meta.json["seed"] == {"users": 200, "conversations": 1000, "messages": 20000}` (Review Focus 5).
- [ ] **Step 3: Run the full automated suite** (`uv run pytest tests -v --cov=. --cov-report=term-missing`) and save the output to `bench/results/phase1/pytest.txt`.
- [ ] **Step 4: Run `ramp`** for all 7 workloads. Close other heavy applications first and note in `--label` anything unusual.
- [ ] **Step 5: Freeze rates.** For each workload take the highest RPS in the `ramp` run where `error_rate < 1 %` and write 50 % and 80 % of it to `tests/load/rates.json`. These numbers are now fixed for Phases 2 and 3.
- [ ] **Step 6: Run `rate`** for all 7 workloads at both frozen rates.
- [ ] **Step 6b: Time-ordered-id reference.** Re-run `database-write`, `database-mixed` and `chatbot` (`ramp`, then `rate` at the same frozen rates) with `--env ID_STRATEGY=uuidv7 --label uuidv7`. This is what production runs today; it shows what random ids cost or gain on Postgres, and it is reported beside the comparison, not inside it.
- [ ] **Step 7: Sanity-check** the numbers against expectations: `auth` logins/s capped near (1 CPU ÷ Argon2 hash time); `chatbot` RPS × 0.8 s ≈ open streams; `stats.csv` shows which container hits its CPU limit in each workload. Write three sentences per workload in `bench/results/phase1/NOTES.md`: what saturated first, and the evidence.
- [ ] **Step 8: Commit** `bench: phase 1 baseline results` (summaries, stats, meta; not raw).

**Limitation to state in the report:** k6, the API, and the databases share one 8-thread machine. Numbers show relative shape between phases, not production capacity. If a second machine is available, run k6 there with `BASE_URL=http://<host-ip>:58080` and bind nginx to the LAN interface for that run only.

---

# Phase F — Multiple instances and CockroachDB (spec §7 Phases 2–3)

### Task F1: CockroachDB compatibility spike (gate)

Nothing later in this phase is safe to build until these four answers are written down. Time-box: half a day.

**Files:**
- Modify: `backend/app/pyproject.toml` (`uv add --group bench sqlalchemy-cockroachdb`)
- Create: `docs/multi-instance.md` (section "CockroachDB compatibility"), `infra/bench/crdb.version`

- [ ] **Step 1:** Pick the current stable CockroachDB image tag, `docker pull` it, and write tag + digest to `infra/bench/crdb.version`. Start one node: `cockroach start-single-node --insecure`. Create database `chatbot_test`.
- [ ] **Step 2: Question 1 — driver.** With `DB_SCHEME=cockroachdb+asyncpg`, `DB_QUERY=ssl=disable`, does `create_async_engine` connect and run `SELECT 1`? Does insecure mode accept the dummy password that `Settings` requires? Record yes/no and the error text.
- [ ] **Step 3: Question 2 — ids and isolation.** Confirm `SELECT gen_random_uuid();` works (Task X4 makes the schema use it under `ID_STRATEGY=random`). Run `SELECT uuidv7();` too and record the result for the docs. Then check READ COMMITTED (D3): `SHOW CLUSTER SETTING sql.txn.read_committed_isolation.enabled;`, enable it if it is off, run `ALTER DATABASE chatbot_test SET default_transaction_isolation = 'read committed';`, reconnect, and confirm `SHOW transaction_isolation;` prints `read committed`. Record the exact statements that worked on this version.
- [ ] **Step 4: Question 3 — migrations.** Run `alembic upgrade head` against the node with `ID_STRATEGY=random`. List every migration that fails and why (CockroachDB restricts some `ALTER` statements inside transactions).
- [ ] **Step 5: Question 4 — the suite.** Write `tests/test.crdb.env` (as `test.env` but port 56257, `DB_SCHEME`, `DB_QUERY`) and run `APP_ENV_FILE=tests/test.crdb.env uv run pytest tests -v`. Record every failure with its cause. `test.crdb.env` also sets `ID_STRATEGY=random`. Expect differences around `TRUNCATE` speed. Under READ COMMITTED the concurrency tests should behave as on Postgres; a 40001 error here means the isolation setting did not take effect.
- [ ] **Step 6: Commit** `spike: cockroachdb compatibility findings`. If Steps 2–5 need app changes beyond what is listed here, stop and revise the tasks below before continuing.

### Task F2: Distributed stack

**Files:** Create `infra/bench/bench.crdb.env`, `infra/bench/compose.crdb.yml`, `infra/bench/haproxy/haproxy.cfg`, `infra/bench/nginx/phase2.conf`, `infra/bench/nginx/phase3.conf`

**Interfaces:**
- Produces compose project `chatbot-bench-crdb`: `crdb1`–`crdb5` (0.5 CPU / 1 GB each, `--cache=.25 --max-sql-memory=.25`, `--join=crdb1,crdb2,crdb3`), `crdb-init` (one-shot `cockroach init`, creates `chatbot_bench`, then applies the READ COMMITTED statements recorded in Task F1 Step 3), `crdb-lb` (HAProxy, TCP 26257, health check `GET /health?ready=1` on each node's 8080), `redis`, `migrate`, `seed`, `api1`, `api2`, `api3` (profile `phase3`), `nginx`. The backend image is built with `UV_EXTRA_ARGS="--group bench"`.
- `PHASE=phase2|phase3` selects the nginx conf and whether `api3` starts. `run_bench.py --phase` sets it.

- [ ] **Step 1:** Write the files. `phase2.conf` and `phase3.conf` differ from `phase1.conf` only in the `upstream` server list (round-robin, the default, so distribution is easy to verify). API containers reach the database only through `crdb-lb`, so a dead node is routed around instead of taking an API instance with it.
- [ ] **Step 2:** Rebuild Phase 1's image with the same `UV_EXTRA_ARGS` so all phases run an identical image. Re-run one Phase 1 `rate` workload and confirm p95 is within run-to-run noise of the earlier result; if not, re-run the Phase 1 set.
- [ ] **Step 3: Verify the cluster.** `PHASE=phase2 docker compose -f infra/bench/compose.crdb.yml up -d --build --wait`. `cockroach node status --insecure` lists 5 live nodes. Record the *actual* replication settings in `docs/multi-instance.md`: output of `SHOW ZONE CONFIGURATION FROM DATABASE chatbot_bench;` (`num_replicas`) and `SHOW RANGES FROM DATABASE chatbot_bench WITH DETAILS;` (which nodes hold replicas and leases). Do not write a fault-tolerance claim yet; Task G3 measures it.
- [ ] **Step 4: Verify load balancing.** 300 `GET /health/` requests through nginx, tally the `X-Upstream` header: each of the 2 (or 3) instances serves within ±10 % of an equal share.
- [ ] **Step 5: Commit** `bench: cockroachdb cluster with multiple api instances`.

### Task F3: Correctness on the distributed stack

**Files:** Create `tests/distributed/test_cross_instance.py`, `tests/distributed/test_crdb_contention.py`, `tests/distributed/conftest.py`

**Interfaces:**
- `tests/distributed/conftest.py`: skips the folder unless `STACK_URLS` is set (comma-separated instance URLs, e.g. `http://127.0.0.1:58001,http://127.0.0.1:58002`); fixtures `instance_a`, `instance_b` → `httpx.AsyncClient` per instance. These tests talk to the running stack over real HTTP and use the seeded bench users.

- [ ] **Step 1: Write cross-instance tests.**
  - log in on A → `GET /api/auth/me` on B is 200 with the same user id.
  - refresh on B with the cookie issued by A → 200; the old cookie on A → 409 (inside grace).
  - log out on B → the access token is 401 on A.
  - create a conversation on A → B returns it.
  - chat on A, then chat on B in the same conversation → B's reply starts with `fake-reply h=2` (it read A's turn from shared Redis), and `GET …/messages` on A shows 4 rows.
  - `POST /api/chat` quota: with the stack's limit temporarily set to 3 via a second env file, 2 chats on A and 2 on B → the fourth is 429.
- [ ] **Step 2: Write contention tests** (CockroachDB only): 20 concurrent refreshes of one session split across A and B → exactly one 200 and no 5xx. 20 concurrent conversation creations by one user across A and B → 20 rows. Count any 5xx and read `txn.restarts` before/after.
- [ ] **Step 3:** Run the in-process suite against the cluster (`APP_ENV_FILE=tests/test.crdb.env uv run pytest tests/integration tests/concurrency -v`) and the distributed tests (`STACK_URLS=… uv run pytest tests/distributed -v`). Save both outputs under `bench/results/phase2/`. Repeat with `PHASE=phase3` and three URLs into `bench/results/phase3/`.
- [ ] **Step 4 (D3): see what SERIALIZABLE would have done.** Reset the database default (`ALTER DATABASE chatbot_bench RESET default_transaction_isolation;`), restart the API containers, and re-run only `tests/distributed/test_crdb_contention.py`. Record the 5xx count and the `txn.restarts` delta beside the READ COMMITTED numbers in `docs/multi-instance.md`, then restore READ COMMITTED. This is the evidence for the D3 choice: under SERIALIZABLE CockroachDB asks the client to retry (SQLSTATE 40001) and this app has no retry code, so those surface as 500s.
- [ ] **Step 5: Commit** `test: cross-instance consistency and cockroachdb contention`.

### Task F4: Phase 2 and Phase 3 benchmarks

**Files:** Create `bench/results/phase2/…`, `bench/results/phase3/…`

- [ ] **Step 1:** Extend `run_bench.py`'s `db.json` collection for CockroachDB (metrics named in Task E4) and per-node `stats.csv` rows.
- [ ] **Step 2: Phase 2.** Run all 7 workloads with `--profile ramp`, then `--profile rate` at both frozen rates from `rates.json`. Same scripts, same rates, same warm-up, same dataset.
- [ ] **Step 3: Phase 3.** Same again with `--phase phase3`.
- [ ] **Step 4:** For each phase add `NOTES.md` as in Task E4 Step 7, plus: nginx request share per instance; connection count per instance and in total (`DB_POOL_SIZE` × instances vs what the cluster shows); whether CPU is spread across the CockroachDB nodes (with random ids it should be — check the console's Hot Ranges page at `:58888`). Optional labeled run to see the hot range of F21 for yourself: `database-write` with `--env ID_STRATEGY=uuidv7 --label uuidv7`, if Task F1 found a working `uuidv7()`; skip it otherwise.
- [ ] **Step 5:** Answer in `bench/results/phase3/NOTES.md`, with the file and field each answer comes from: did a third instance raise `ramp` RPS? did it lower `rate` p95? which container was at its CPU limit — API, CockroachDB, Redis, or the load generator? If k6's host CPU was saturated, say the result is inconclusive.
- [ ] **Step 6: Commit** `bench: phase 2 and phase 3 results`.

---

# Phase G — Resilience (spec §8)

### Task G1: Chaos harness and write ledger

**Files:** Create `infra/bench/chaos.py`, `infra/bench/ledger.py`

**Interfaces:**
- `python infra/bench/chaos.py --scenario {api-kill,crdb-kill-1,crdb-kill-2,redis-kill} --workload W --rate N` — runs k6 `rate` for 240 s; at t = 60 s runs `docker kill` on the target(s); at t = 150 s `docker start`; samples cluster state every 5 s. Writes to `bench/results/resilience/<scenario>/<timestamp>/`: `timeline.csv` (per second: requests, failures, p95, from `raw.csv.gz`), `cluster.csv` (live nodes, `ranges_unavailable`, `ranges_underreplicated`), `upstreams.csv` (nginx requests per instance per 5 s), and `result.json`: `failed_requests`, `error_window_s` (first to last second above 1 % failures), `recovery_after_kill_s`, `recovery_after_restart_s`, `time_to_fully_replicated_s`.
- `python infra/bench/ledger.py run --workers 20 --duration 240` — each worker creates conversations with a unique title and sends chat turns with a unique marker in the message, appending every acknowledged write to `ledger.jsonl`. Every logical write carries its own `Idempotency-Key` (Task X3); a failed or timed-out request is retried up to 3 times with the same key and payload, and a 409 is waited out and retried. `--no-idempotency` omits the header. `ledger.py verify` compares the ledger to the database and writes `consistency.json`: `acked`, `lost` (acked but missing), `duplicated` (present more than once), `unacked_present` (failed to the client but committed).

- [ ] **Step 1:** Write both scripts. Guard: `chaos.py` acts only on containers labeled `com.docker.compose.project=chatbot-bench-crdb` and exits if the label is absent or `BASE_URL` is not loopback.
- [ ] **Step 2: Test the guard:** `chaos.py --scenario api-kill` with `BASE_URL=http://example.com` exits non-zero without touching Docker.
- [ ] **Step 3: Dry run** `api-kill` at a low rate and confirm all four output files are produced.
- [ ] **Step 4: Commit** `bench: chaos harness and write ledger`.

### Task G2: API instance failure

- [ ] **Step 1:** On the Phase 2 stack, run `chaos.py --scenario api-kill --workload conversations --rate <50 % rate>` and again with `--workload chatbot`. Run `ledger.py run` alongside the second one, then `ledger.py verify`.
- [ ] **Step 2:** From the outputs, record in `bench/results/resilience/NOTES.md`: seconds until nginx stopped sending to the dead instance (`upstreams.csv`); failed requests and error window; whether in-flight SSE streams on the killed instance ended without `done` (`chat_incomplete`); seconds until the restarted instance received traffic again; any document left in `processing` (F17); `lost` must be 0 — if not, that is the headline finding.
- [ ] **Step 3:** Repeat on the Phase 3 stack. One of three instances dying should cost less than one of two; state whether the data agrees.
- [ ] **Step 4: Commit** `bench: api failure experiments`.

### Task G3: Database failure and data consistency

- [ ] **Step 1: One node.** `chaos.py --scenario crdb-kill-1` with `ledger.py` running. Record: availability during the outage, `error_window_s`, in-flight request errors (interrupted connections surface as 500s; `pool_pre_ping` only protects new checkouts), `txn.restarts`, and `time_to_fully_replicated_s` after the restart.
- [ ] **Step 2: Two nodes at once.** `crdb-kill-2`. Compare what happened with what the recorded `num_replicas` from Task F2 Step 3 predicts: with 3 replicas per range, losing 2 nodes together can leave some ranges without a quorum; with 5, it should not. Write down the observed `ranges_unavailable` and which requests failed. This is the measurement the spec asks for in place of an assumption.
- [ ] **Step 3: Optional variant.** `ALTER DATABASE chatbot_bench CONFIGURE ZONE USING num_replicas = 5;`, wait for `ranges_underreplicated = 0`, repeat Step 2 under `--label rf5`.
- [ ] **Step 4: Redis.** `chaos.py --scenario redis-kill --workload chatbot`: after Task X2 chat should keep answering. Record the error rate during the outage (only requests in flight at the kill should fail), p95 during the outage against before it (the 1 s connect timeout shows here), and whether history is rebuilt from the database after restart (reply `h=` value is non-zero for an existing conversation). `GET /health/` is expected to be 503 throughout, so confirm nginx did not eject the instances for it.
- [ ] **Step 5: Consistency.** For every scenario, `ledger.py verify` must report `lost == 0` and `duplicated == 0`.
- [ ] **Step 6: Show what the header buys.** Repeat `crdb-kill-1` once with `ledger.py run --no-idempotency` and record `duplicated`. A count above 0 here, against 0 in Step 5, is the measured effect of Task X3.
- [ ] **Step 7: Commit** `bench: database failure and consistency experiments`.

---

# Phase H — Report and documentation (spec §9, deliverables 8–9)

### Task H1: Comparative report and docs

**Files:** Create `infra/bench/report.py`, `docs/benchmarks/REPORT.md`, `docs/testing.md`; finish `docs/multi-instance.md`

**Interfaces:**
- `python infra/bench/report.py` reads only files under `bench/results/` and writes `docs/benchmarks/REPORT.md`. For each workload it emits the spec's table (API instances, database nodes, RPS, RPM, average, p95, p99, error rate, CPU, memory per phase), taking RPS from the `ramp` run and latency from the 80 % `rate` run, each cell footnoted with its source file. CPU and memory are the mean and peak from `stats.csv`, per container role. A missing result prints `not measured`.

- [ ] **Step 1: Write a test** `tests/unit/test_report.py`: given a temp results tree with only Phase 1 present, the generated table has Phase 1 numbers equal to the fixture's `summary.json` and `not measured` in every Phase 2 and 3 cell.
- [ ] **Step 2:** Write `report.py`; run the test. Expected: PASS.
- [ ] **Step 3:** Generate the report. Below the generated tables, hand-write: the single-host limitation, what was held constant, the bottleneck per phase with evidence, the resilience table from `result.json` files, the consistency table, the Postgres `uuidv7` reference runs beside the random-id comparison, the SERIALIZABLE vs READ COMMITTED contention numbers, and decisions D2–D5 with the evidence for each.
- [ ] **Step 4:** Write `docs/testing.md`: prerequisites; starting the test containers; the three pytest commands; how fakes and `ScriptedLLM` work; running k6 by hand and through `run_bench.py`; running chaos scenarios; the safety guards and what they refuse.
- [ ] **Step 5:** Finish `docs/multi-instance.md` — changes needed to run more than one instance: shared `JWT_SECRET_KEY` and Redis; proxy settings for SSE (`proxy_buffering off`, long read timeout); `TRUST_PROXY_HEADERS` and `X-Real-IP`; pool size × instances vs database connection limit; per-instance state that does not survive an instance (audit queue F18, ingestion F17); the races F14–F16; CockroachDB compatibility results from F1.
- [ ] **Step 6:** Final check: `uv run pytest tests -v --cov=. --cov-report=term-missing` passes from a clean `docker compose -f docker-compose.test.yml up -d --wait`.
- [ ] **Step 7: Commit** `docs: benchmark report, testing guide and multi-instance notes`.

---

## Spec coverage

| Spec section | Tasks |
|---|---|
| §1 Inspect architecture | Findings, A2 |
| §2 Dependencies and test infrastructure | A1–A3 |
| §3 Coverage priorities 1–10 | B2, B3, B3, B4, B4, B5, B5, B6, B6, B7; unit B1; concurrency D1 |
| §4 Chatbot lifecycle and failures | C1, C2 |
| §5 Test execution | A1, D1 Step 5 |
| §6 k6 workloads and metrics | E2–E4 |
| §7 Phases 1–3 | E4, F1–F4 |
| §8 Resilience | G1–G3 |
| §9 Report | H1 |
| §10 Implementation order | Phases A–H follow it |
| Decisions of 2026-11-11 (Argon2, D2–D5) | X1–X4, F1–F3, G3 |
