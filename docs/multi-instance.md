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

### Fixed: the model missed turns after a Redis outage

While Redis is down, chat keeps working and turns are saved only to Postgres. When
Redis came back it still held the list from before the outage, and the model was
given that stale list (finding F28). Now a `chat:user:{u}:conversation:{c}:synced`
key records how many Postgres messages the cached history reflects. Each turn
compares it with a count from Postgres; on a mismatch, or with no marker, the
history and summary are rebuilt from Postgres. The marker moves on only when a turn
reached both stores. Pinned by `test_history_not_stale_after_outage` and
`test_history_in_sync_with_postgres_is_read_from_redis`.

Cost: one indexed `COUNT` per chat turn.
