# Multi-instance notes

## Known issues

### Fixed: a client that closed the stream on `done` lost the turn

The turn used to be saved after `done` was sent, and the save was skipped once the
client had gone, so a client that hung up on `done` lost the turn (0 rows in 16 of
16 runs, 2026-11-13; finding F10, Review Focus 3). The save now starts in its own
task before `done` and keeps running after a disconnect, and an `Idempotency-Key`
lock is held until it ends. Pinned by `test_disconnect_after_done_keeps_turn` and
`test_retry_after_hanging_up_at_done_never_runs_the_model_twice` in
`backend/app/tests/integration/test_chat_failures.py`.

Still true: a save in flight lives in that instance's memory. If the instance is
killed in the moment between `done` and the end of the save, the turn is lost.

### The model can miss turns after a Redis outage

While Redis is down, chat keeps working and reads history from Postgres, but the
turns are saved only to Postgres. When Redis returns it still holds the list from
before the outage, and the model is given that stale list. Observed in
`tests/integration/test_chat_failures.py::test_history_not_stale_after_outage`
(xfail). See finding F28 in `docs/superpowers/plans/2026-11-11-backend-testing-scalability.md`.
The fix, comparing with Postgres before trusting the cache, is a follow-up.
