# Multi-instance notes

## Known issues

### A client that closes the stream on `done` can lose the turn

In `backend/app/services/graph/runner.py` the turn is saved after the `done`
event is sent, and the save is skipped if the client has already disconnected.
A client that closes the connection as soon as it receives `done` therefore
never gets its messages written to Postgres (or Redis).

Observed in `tests/integration/test_chat_failures.py::test_disconnect_after_done_loses_turn`:
0 rows saved in 16 of 16 counted runs against a real socket (2026-11-13). See finding F10 and Review
Focus 3 in `docs/superpowers/plans/2026-11-11-backend-testing-scalability.md`.

### The model can miss turns after a Redis outage

While Redis is down, chat keeps working and reads history from Postgres, but the
turns are saved only to Postgres. When Redis returns it still holds the list from
before the outage, and the model is given that stale list. Observed in
`tests/integration/test_chat_failures.py::test_history_not_stale_after_outage`
(xfail). See finding F28 in `docs/superpowers/plans/2026-11-11-backend-testing-scalability.md`.
The fix, comparing with Postgres before trusting the cache, is a follow-up.
