import { mainSeconds } from "./config.js";

const MAIN = "{scenario:main}";

function vals(data, name) {
  const m = data.metrics[`${name}${MAIN}`];
  return m ? m.values : null;
}

function num(x) {
  return typeof x === "number" && isFinite(x) ? x : 0;
}

export function buildSummary(data) {
  const reqs = vals(data, "http_reqs");
  const dur = vals(data, "http_req_duration");
  const failed = vals(data, "http_req_failed");
  const checks = vals(data, "checks");
  const timeouts = vals(data, "timeout_rate");
  const dropped = vals(data, "dropped_iterations");
  const seconds = mainSeconds() || data.state.testRunDurationMs / 1000;
  const total = num(reqs && reqs.count);
  const rps = total / seconds;
  return {
    total_requests: total,
    rps,
    rpm: rps * 60,
    vus_max: num(data.metrics.vus_max && data.metrics.vus_max.values.max),
    avg_ms: num(dur && dur.avg),
    p50_ms: num(dur && dur.med),
    p95_ms: num(dur && dur["p(95)"]),
    p99_ms: num(dur && dur["p(99)"]),
    error_rate: num(failed && failed.rate),
    timeout_rate: num(timeouts && timeouts.rate),
    dropped_iterations: num(dropped && dropped.count),
    checks_rate: num(checks && checks.rate),
  };
}

function text(data, s) {
  const lines = ["", "== main scenario summary =="];
  for (const [k, v] of Object.entries(s)) {
    lines.push(`${k.padEnd(20)} ${+v.toFixed(4)}`);
  }
  for (const name of ["chat_ttfb", "chat_duration", "chat_incomplete"]) {
    const v = vals(data, name);
    if (v) lines.push(`${name.padEnd(20)} ${JSON.stringify(v)}`);
  }
  const logins = data.metrics.session_logins;
  if (logins) lines.push(`${"session_logins".padEnd(20)} ${logins.values.count}`);
  return lines.join("\n") + "\n";
}

export function handleSummary(data) {
  const s = buildSummary(data);
  const dir = __ENV.RESULTS_DIR || ".";
  return {
    [`${dir}/summary.json`]: JSON.stringify(s, null, 2),
    stdout: text(data, s),
  };
}
