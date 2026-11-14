# Phase 1 baseline: one API instance, one Postgres node

Run on 2026-11-13. One API process (1 CPU, 512 MB) behind nginx (0.5 CPU), Postgres 18
(2 CPU, 1 GB), Redis 7 (0.5 CPU), seeded with 200 users, 1,000 conversations and 20,000
messages. External services are faked; a chat reply streams 40 tokens 20 ms apart. k6
v2.3.0 runs on the same 8-thread machine, so these numbers compare setups and do not
predict production capacity.

## Ramp (10 → 25 → 50 → 100 VUs, 90 s held at each level)

Requests per second at each level, with p95. No level of any workload had an error.

| Workload | 10 VUs | 25 VUs | 50 VUs | 100 VUs |
|---|---|---|---|---|
| health | 103 (212 ms) | 135 (407 ms) | **137** (984 ms) | 134 (2.5 s) |
| auth | 29 (831 ms) | **33** (1.7 s) | 28 (4.0 s) | 33 (7.2 s) |
| database-read | 67 (309 ms) | 70 (802 ms) | **89** (1.5 s) | 80 (3.7 s) |
| database-write | 67 (307 ms) | 48 (1.0 s) | 55 (2.4 s) | **71** (4.4 s) |
| database-mixed | 65 (345 ms) | **76** (768 ms) | 75 (1.8 s) | 73 (3.9 s) |
| conversations | 5 (28 ms) | 13 (37 ms) | 25 (119 ms) | **43** (1.3 s) |
| chatbot (turns/s) | 9.7 (1.4 s) | **12.5** (3.3 s) | 12.3 (5.2 s) | 10.8 (11.1 s) |

Once the API is saturated, throughput stays flat and only latency grows. Levels past
saturation move by ±15 % between levels (database-write: 67, 48, 55, 71). That is the
run-to-run noise on this machine; read smaller differences in this file with that in
mind.

## Frozen rates

`backend/app/tests/load/rates.json` holds 50 % and 80 % of the best ramp level, in k6
iterations per second (what `RATE` sets), with requests per iteration alongside.

## Fixed rate (3 minutes)

| Workload | Rate (iter/s) | req/s | p50 | p95 | p99 | Errors | Dropped |
|---|---|---|---|---|---|---|---|
| health | 34 | 68 | 9 ms | 78 ms | 195 ms | 0 | 0 |
| health | 55 | 110 | 153 ms | 1.19 s | 3.33 s | 0 | 20 |
| auth | 4 | 16 | 15 ms | 69 ms | 116 ms | 0 | 0 |
| auth | 7 | 28 | 15 ms | 159 ms | 363 ms | 0 | 0 |
| database-read | 22 | 44 | 95 ms | 626 ms | 955 ms | 0 | 0 |
| database-read | 35 | 70 | 91 ms | 655 ms | 919 ms | 0 | 0 |
| database-write | 35 | 35 | 17 ms | 116 ms | 338 ms | 0 | 0 |
| database-write | 57 | 57 | 175 ms | 995 ms | 1.37 s | 0.02 % | 0 |
| database-mixed | 21 | 38 | 14 ms | 52 ms | 103 ms | 0 | 0 |
| database-mixed | 34 | 61 | 24 ms | 509 ms | 740 ms | 0 | 0 |
| conversations | 7 | 22 | 17 ms | 31 ms | 54 ms | 0 | 0 |
| conversations | 11 | 34 | 19 ms | 110 ms | 300 ms | 0 | 0 |
| chatbot | 6 | 6 | 859 ms | 940 ms | 978 ms | 0 | 0 |
| chatbot | 10 | 10 | 899 ms | 1.65 s | 2.50 s | 0 | 0 |

No chat stream ended without `done` in any run.

## What saturated first

**health.** The API container's single CPU: it averaged 96 % (p90 100 %) in the ramp,
while Postgres used 17 % of its 2 CPUs. Throughput stopped at about 137 req/s from 25 VUs
on, and latency grew roughly linearly with VUs. Every `/auth/me` loads the session, the
user and their roles from Postgres, but each query takes about 0.13 ms, so the time goes
to Python.

**auth.** Also the API CPU (97 % mean), from Argon2id hashing: each iteration does one
login, and 8.3 iterations/s on one core means about 120 ms of CPU per iteration, which
fits one hash (19 MiB, 2 passes) plus three cheap requests. The fixed-rate runs stay fast
because at 4–7 logins/s the hashes don't queue. Postgres shows a second, smaller effect:
the user-row lock added for F15 (`SELECT … FOR UPDATE` on `users`) averaged 85 ms, against
0.1–3 ms for every other statement. A plain `FOR UPDATE` also conflicts with the
`KEY SHARE` lock that each foreign-key insert into `audit_logs` and `sessions` takes on
the same user row, so a login waits for that user's audit writes. `FOR NO KEY UPDATE`
would still serialize logins without that conflict. Not yet changed.

**database-read.** The API CPU (96 %, p90 101 %); Postgres reached 26 % at p90 and its
top statements average 0.12–0.14 ms. The peak was 89 req/s at 50 VUs. In the fixed-rate
runs the API was already at 85 % CPU at 22 iterations/s, so p95 is about 640 ms at both
rates. Serialising each conversation and its message history (the endpoint returns full
message parts) in Python is the likely cost, so the read path is the one to profile first.

**database-write.** The API CPU (95 %); Postgres used 28 % at p90, and the insert into
`conversations` averages 0.17 ms. The peak was 71 req/s. At 57 iterations/s, 0.02 % of
requests failed (about 2 in 10,000); everything else completed.

**database-mixed.** The API CPU (95 %), Postgres 25 % at p90. It peaks at 76 req/s,
between read-only and write-only as an 80/20 mix should. At 80 % of the peak, p95 is
509 ms, against 52 ms at 50 %.

**conversations.** Never saturated: each iteration waits 1–3 s between requests, so
100 VUs only reach 43 req/s. The API averaged 41 % CPU. Its p95 rose to 1.3 s at 100 VUs
because CPU peaks reached 92 % in bursts. A real limit needs more VUs or a fixed rate
above 11 iterations/s.

**chatbot.** The API CPU (88 % mean, p90 100 %): Postgres used 11 % and the slowest
statement, the message insert, averages 0.32 ms. At 12.5 turns/s with replies taking
about 0.85 s, about 11 streams are open at once (rate × duration). At 6 turns/s, p95 is
940 ms, which is barely above the 0.8 s the fake model takes, so the app adds little
overhead until the CPU is busy.

## Time-ordered ids (uuidv7) reference

The same workloads with `ID_STRATEGY=uuidv7`, the production setting. The table above
uses random ids (`ID_STRATEGY=random`), which is what CockroachDB will need in phase 3.

| Workload | Ramp peak, random → uuidv7 | p95 at 50 %, random → uuidv7 | p95 at 80 %, random → uuidv7 |
|---|---|---|---|
| database-write | 71 → 64 req/s | 116 ms → 984 ms | 995 ms → 1.39 s |
| database-mixed | 76 → 60 req/s | 52 ms → 64 ms | 509 ms → 997 ms |
| chatbot | 12.5 → 11.1 turns/s | 940 ms → 950 ms | 1.65 s → 1.34 s |

uuidv7 comes out slightly worse on the database workloads and about even on chatbot,
but this doesn't show that uuidv7 is slower. Postgres is below 40 % CPU in every run, so
the id strategy can only change a 0.2 ms insert, while the API's CPU decides the
throughput. The differences are within the ±15 % noise above. The database-write
50 % gap comes from a p99 of 4.9 s, which points to one stall, not a slower path. The
index-locality benefit of time-ordered ids shows when the index outgrows memory; with
20,000 rows it fits.

## Notes on the runs

- The first fixed-rate batch was discarded. In a fixed-rate run, k6 starts iterations on
  up to 500 VUs that have not logged in yet, and each one first did an Argon2 login, so
  the first ~75 s measured a login storm (p95 18 s at health's 50 % rate). Since
  `a209a90`, a k6 `setup()` logs in all 200 seeded users before the test, and the
  measured window contains no logins. Ramp runs add VUs gradually and are unaffected.
- Six of the seven ramp runs and the three uuidv7 ramp runs have `git_dirty: true` in
  `meta.json`. They ran at commit `3ad946e` (uuidv7: `189a5f3`), and nothing under
  `backend/` or `infra/` was modified: the flag came from untracked result folders and,
  later, an uncommitted README edit. Since `189a5f3` the flag ignores `bench/results`,
  and every fixed-rate run is clean.
- `raw.csv.gz` is not committed.
