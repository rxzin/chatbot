# Backend tests

Run everything from `backend/app`.

## Prerequisites

Start the disposable test stack (Postgres 18 on 55432, Redis on 56379):

    docker compose -f docker-compose.test.yml up -d --wait

Tests read only `backend/app/tests/test.env`, never `backend/app/.env`. No test calls a real external service.

## Commands

    uv run pytest tests -v --cov=. --cov-report=term-missing
    uv run pytest tests/integration -v
    uv run pytest tests/concurrency -v

Unit tests (`tests/unit`) run without Docker.

## Current results

Full suite: 222 passed, 4 xfailed. Coverage TOTAL: 83% (3112 statements, 533 missed).

`tests/concurrency`: 11 passed, 4 xfailed, identical over three consecutive runs (about 44 s; the F30 xfail waits for the 30 s pool timeout).

## Known findings in the tests

`xfail(strict=False)` tests state the desired behavior of a known defect; a passing test next to each pins today's behavior. Findings: F14 (Redis history race), F15 (session cap), F16 (duplicate registration returns 500), F30 (DB pool exhausted by concurrent chats). See `docs/superpowers/plans/2026-11-11-backend-testing-scalability.md`.
