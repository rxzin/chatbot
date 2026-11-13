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
