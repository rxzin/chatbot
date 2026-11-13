#!/usr/bin/env python3
"""Benchmark runner (plan Task E4). Python standard library only.

Run from the repo root (any Python 3.9+; no third-party packages):

    python infra/bench/run_bench.py --phase phase1 --workload health --profile smoke
    python infra/bench/run_bench.py --phase phase1 --workload chatbot --profile rate --rate 40
    python infra/bench/run_bench.py --phase phase1 --workload chatbot --profile smoke \
        --env FAKE_LLM_TOKEN_DELAY_MS=10 --label override-check

Every run: `down -v`, `up -d --build --wait`, reset pg_stat_statements, run k6
while sampling docker stats, then snapshot Postgres and Redis and write
bench/results/<phase>/<workload>-<profile>[-<label>]/<UTC timestamp>/.
The stack is left running afterwards.
"""
import argparse
import csv
import datetime as dt
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
LOAD_DIR = os.path.join(REPO, "backend", "app", "tests", "load")
RESULTS = os.path.join(REPO, "bench", "results")
BENCH_ENV = os.path.join(HERE, "bench.env")
RUN_ENV = os.path.join(HERE, ".run.env")  # temp copy with --env overrides (git-ignored)

WORKLOADS = {
    "health": ("health.js", None),
    "auth": ("auth.js", None),
    "database-read": ("database.js", "read"),
    "database-write": ("database.js", "write"),
    "database-mixed": ("database.js", "mixed"),
    "conversations": ("conversations.js", None),
    "chatbot": ("chatbot.js", None),
}
PHASES = {"phase1": ("compose.phase1.yml", "chatbot-bench-p1")}
# TODO(Phase F): phase2/phase3 use compose.crdb.yml (project chatbot-bench-crdb,
# PHASE=phase2|phase3, CockroachDB metrics in db.json). Not written yet.
FUTURE_PHASES = {"phase2": "compose.crdb.yml", "phase3": "compose.crdb.yml"}

DB_CMD = ["exec", "-T", "db", "psql", "-U", "chatbot_bench", "-d", "chatbot_bench", "-At", "-c"]
STAGE_VUS = [10, 25, 50, 100]
WARMUP_S, RAMP_S, HOLD_S = 30, 15, 90


def run(cmd, check=True, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed ({r.returncode}):\n{r.stdout}\n{r.stderr}")
    return r


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


class Stack:
    def __init__(self, compose_file, project, env):
        self.base = ["docker", "compose", "-p", project, "-f", compose_file]
        self.project = project
        self.env = env

    def compose(self, *args, check=True, stream=False):
        if stream:
            r = subprocess.run(self.base + list(args), env=self.env)
            if check and r.returncode:
                raise RuntimeError(f"compose {' '.join(args)} failed ({r.returncode})")
            return r
        return run(self.base + list(args), check=check, env=self.env)

    def psql_json(self, sql):
        out = self.compose(*DB_CMD, sql).stdout.strip()
        return json.loads(out) if out else None

    def container_ids(self):
        return [c for c in self.compose("ps", "-q").stdout.split() if c]


def write_run_env(overrides):
    with open(BENCH_ENV, encoding="utf-8") as f:
        lines = f.read().splitlines()
    pending = dict(overrides)
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if "=" in line and not line.lstrip().startswith("#") and key in pending:
            out.append(f"{key}={pending.pop(key)}")
        else:
            out.append(line)
    out += [f"{k}={v}" for k, v in pending.items()]
    with open(RUN_ENV, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")


def seed_counts(stack):
    logs = stack.compose("logs", "--no-log-prefix", "seed").stdout
    found = None
    for line in logs.splitlines():
        line = line.strip()
        if line.startswith("{") and '"users"' in line:
            try:
                found = json.loads(line)
            except ValueError:
                pass
    if not found:
        raise RuntimeError("seed counts not found in `compose logs seed`")
    return found


# ---- docker stats sampler -------------------------------------------------
_UNITS = {"b": 1 / 1048576, "kib": 1 / 1024, "kb": 1 / 1024, "mib": 1, "mb": 1, "gib": 1024, "gb": 1024}


def mem_mib(text):
    m = re.match(r"\s*([\d.]+)\s*([A-Za-z]+)", text)
    return float(m.group(1)) * _UNITS.get(m.group(2).lower(), 1) if m else 0.0


class StatsSampler(threading.Thread):
    def __init__(self, ids, path, interval=2.0):
        super().__init__(daemon=True)
        self.ids, self.path, self.interval = ids, path, interval
        self.stop_evt = threading.Event()

    def run(self):
        with open(self.path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "container", "cpu_pct", "mem_mib"])
            while not self.stop_evt.is_set():
                t0 = time.time()
                r = run(["docker", "stats", "--no-stream", "--format",
                         "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}"] + self.ids, check=False)
                ts = utcnow().isoformat(timespec="seconds")
                for line in r.stdout.splitlines():
                    parts = line.split("|")
                    if len(parts) == 3:
                        w.writerow([ts, parts[0], parts[1].strip().rstrip("%"),
                                    round(mem_mib(parts[2].split("/")[0]), 2)])
                f.flush()
                self.stop_evt.wait(max(0.0, self.interval - (time.time() - t0)))

    def stop(self):
        self.stop_evt.set()
        self.join(timeout=15)


# ---- Postgres / Redis snapshots ------------------------------------------
def pg_snapshot(stack):
    return stack.psql_json(
        "SELECT json_build_object("
        "'pg_stat_database', (SELECT row_to_json(d) FROM pg_stat_database d WHERE datname='chatbot_bench'),"
        "'connections', (SELECT count(*) FROM pg_stat_activity WHERE datname='chatbot_bench'))")


def pg_top_statements(stack):
    return stack.psql_json(
        "SELECT COALESCE(json_agg(t), '[]'::json) FROM ("
        "SELECT calls, round(total_exec_time::numeric,2) AS total_exec_time, "
        "round(mean_exec_time::numeric,3) AS mean_exec_time, rows, left(query,200) AS query "
        "FROM pg_stat_statements WHERE dbid=(SELECT oid FROM pg_database WHERE datname='chatbot_bench') "
        "ORDER BY total_exec_time DESC LIMIT 20) t")


def redis_snapshot(stack):
    out = stack.compose("exec", "-T", "redis", "redis-cli", "INFO", "everything").stdout
    info = {}
    for line in out.splitlines():
        if ":" in line and not line.startswith("#"):
            k, v = line.strip().split(":", 1)
            info[k] = v
    snap = {k: info.get(k) for k in
            ("used_memory", "used_cpu_sys", "used_cpu_user", "instantaneous_ops_per_sec")}
    cmds = {}
    for k, v in info.items():
        if k.startswith("cmdstat_"):
            d = dict(p.split("=") for p in v.split(","))
            cmds[k[len("cmdstat_"):]] = {"calls": int(d["calls"]), "usec_per_call": float(d["usec_per_call"])}
    snap["commandstats"] = cmds
    return snap


# ---- stages.json ----------------------------------------------------------
def windows_for(profile):
    if profile == "ramp":
        return [(f"hold_{v}vu", WARMUP_S + RAMP_S + i * (RAMP_S + HOLD_S), HOLD_S, v)
                for i, v in enumerate(STAGE_VUS)]
    if profile == "rate":
        return [("main", None, 180, None)]
    return [("main", None, 30, None)]


def pct(sorted_vals, q):
    if not sorted_vals:
        return 0.0
    i = min(len(sorted_vals) - 1, max(0, int(q * len(sorted_vals) + 0.999999) - 1))
    return sorted_vals[i]


def build_stages(csv_gz, profile, workload):
    # start None = every scenario=main sample (smoke/rate: main only runs that scenario)
    wins = windows_for(profile)
    acc = [{"count": 0, "durs": [], "failed": 0, "nfailed": 0, "inc": 0, "ninc": 0} for _ in wins]
    t0 = None
    rows = []
    with gzip.open(csv_gz, "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            try:
                ts = float(r["timestamp"])
            except (KeyError, ValueError):
                continue
            if t0 is None or ts < t0:
                t0 = ts
            if r.get("scenario") == "main":
                rows.append((ts, r["metric_name"], float(r["metric_value"])))
    if t0 is None:
        return {"test_start_unix": None, "windows": []}
    for ts, name, val in rows:
        rel = ts - t0
        for i, (_, start, length, _) in enumerate(wins):
            if start is None or start <= rel < start + length:
                a = acc[i]
                if name == "http_reqs":
                    a["count"] += int(val)
                elif name == "http_req_duration":
                    a["durs"].append(val)
                elif name == "http_req_failed":
                    a["nfailed"] += 1
                    a["failed"] += 1 if val else 0
                elif name == "chat_incomplete":
                    a["ninc"] += 1
                    a["inc"] += 1 if val else 0
                break
    out = []
    for (label, start, length, vus), a in zip(wins, acc):
        d = sorted(a["durs"])
        w = {"window": label, "vus": vus, "start_s": start, "length_s": length,
             "requests": a["count"], "rps": a["count"] / length,
             "p95_ms": pct(d, 0.95),
             "error_rate": a["failed"] / a["nfailed"] if a["nfailed"] else 0.0}
        if workload == "chatbot":
            w["chat_incomplete_rate"] = a["inc"] / a["ninc"] if a["ninc"] else 0.0
        out.append(w)
    return {"test_start_unix": t0, "windows": out}


# ---- meta -----------------------------------------------------------------
def git(*args):
    return run(["git", "-C", REPO] + list(args), check=False).stdout.strip()


def collect_meta(compose_file, ids):
    info = json.loads(run(["docker", "info", "--format", "{{json .}}"]).stdout)
    limits, images = {}, {}
    for cid in ids:
        d = json.loads(run(["docker", "inspect", cid]).stdout)[0]
        name = d["Name"].lstrip("/")
        hc = d["HostConfig"]
        limits[name] = {"cpus": (hc.get("NanoCpus") or 0) / 1e9, "memory_bytes": hc.get("Memory") or 0}
        images[name] = d["Image"]
    with open(compose_file, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    return {
        "git_sha": git("rev-parse", "HEAD"),
        "git_dirty": bool(git("status", "--porcelain")),
        "k6_version": run(["k6", "version"]).stdout.strip(),
        "image_ids": images,
        "compose_sha256": sha,
        "container_limits": limits,
        "docker_ncpu": info.get("NCPU"),
        "docker_mem_total": info.get("MemTotal"),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", required=True, choices=["phase1", "phase2", "phase3"])
    ap.add_argument("--workload", required=True, choices=list(WORKLOADS))
    ap.add_argument("--profile", required=True, choices=["smoke", "ramp", "rate"])
    ap.add_argument("--rate", type=int)
    ap.add_argument("--label")
    ap.add_argument("--env", action="append", default=[], metavar="KEY=VALUE")
    args = ap.parse_args()

    if args.profile == "rate" and not args.rate:
        ap.error("--profile rate needs --rate N")
    overrides = {}
    for kv in args.env:
        if "=" not in kv:
            ap.error(f"--env needs KEY=VALUE, got {kv!r}")
        k, v = kv.split("=", 1)
        overrides[k] = v

    if args.phase in FUTURE_PHASES:
        sys.exit(f"error: {args.phase} needs infra/bench/{FUTURE_PHASES[args.phase]}, "
                 "which does not exist yet (Phase F).")
    compose_name, project = PHASES[args.phase]
    compose_file = os.path.join(HERE, compose_name)
    if not os.path.exists(compose_file):
        sys.exit(f"error: compose file missing: {compose_file}")

    base_url = os.environ.get("BASE_URL", "http://127.0.0.1:58080")
    if urlparse(base_url).hostname not in ("127.0.0.1", "localhost"):
        sys.exit(f"error: refusing to run: BASE_URL host must be 127.0.0.1 or localhost, got {base_url}")

    script, mix = WORKLOADS[args.workload]
    name = f"{args.workload}-{args.profile}" + (f"-{args.label}" if args.label else "")
    started = utcnow()
    outdir = os.path.join(RESULTS, args.phase, name, started.strftime("%Y%m%dT%H%M%SZ"))
    os.makedirs(outdir)

    env = dict(os.environ)
    write_run_env(overrides)
    env["BENCH_ENV_FILE"] = "./.run.env"
    stack = Stack(compose_file, project, env)

    print(f"[bench] {name}: rebuilding stack", flush=True)
    stack.compose("down", "-v", "--remove-orphans", stream=True)
    stack.compose("up", "-d", "--build", "--wait", stream=True)

    seed = seed_counts(stack)
    ids = stack.container_ids()
    meta = collect_meta(compose_file, ids)
    stack.compose(*DB_CMD, "SELECT pg_stat_statements_reset()")
    db_before = pg_snapshot(stack)
    redis_before = redis_snapshot(stack)

    sampler = StatsSampler(ids, os.path.join(outdir, "stats.csv"))
    kenv = dict(os.environ, PROFILE=args.profile, RESULTS_DIR=outdir, BASE_URL=base_url)
    if args.rate:
        kenv["RATE"] = str(args.rate)
    if mix:
        kenv["MIX"] = mix
    raw = os.path.join(outdir, "raw.csv")
    print("[bench] running k6", flush=True)
    sampler.start()
    k6_start = utcnow()
    try:
        k6 = subprocess.run(["k6", "run", "--out", f"csv={raw}", os.path.join(LOAD_DIR, script)],
                            env=kenv, cwd=LOAD_DIR)
    finally:
        sampler.stop()
    k6_end = utcnow()

    db_after = pg_snapshot(stack)
    top = pg_top_statements(stack)
    redis_after = redis_snapshot(stack)

    if os.path.exists(raw):
        with open(raw, "rb") as fi, gzip.open(raw + ".gz", "wb") as fo:
            shutil.copyfileobj(fi, fo)
        os.remove(raw)
    stages = build_stages(raw + ".gz", args.profile, args.workload) if os.path.exists(raw + ".gz") else {}

    def dump(fn, obj):
        with open(os.path.join(outdir, fn), "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2)

    dump("db.json", {"before": db_before, "after": db_after, "top_statements": top})
    dump("redis.json", {"before": redis_before, "after": redis_after})
    dump("stages.json", stages)
    meta.update({
        "phase": args.phase, "workload": args.workload, "profile": args.profile,
        "rate": args.rate, "label": args.label, "env_overrides": overrides,
        "seed": seed, "k6_exit_code": k6.returncode,
        "start_utc": started.isoformat(), "k6_start_utc": k6_start.isoformat(),
        "k6_end_utc": k6_end.isoformat(), "end_utc": utcnow().isoformat(),
    })
    dump("meta.json", meta)
    if os.path.exists(RUN_ENV):
        os.remove(RUN_ENV)
    print(f"[bench] done: {outdir} (k6 exit {k6.returncode})", flush=True)
    if not os.path.exists(os.path.join(outdir, "summary.json")):
        sys.exit("error: k6 produced no summary.json")


if __name__ == "__main__":
    main()
