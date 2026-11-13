import { Rate } from "k6/metrics";

export const BASE_URL = __ENV.BASE_URL || "http://127.0.0.1:58080";
export const PROFILE = __ENV.PROFILE || "smoke";
export const USERS = 200;
export const PASSWORD = "BenchPassw0rd!";

// Fed by every request through record(); error_code 1050 is k6's request timeout.
export const timeoutRate = new Rate("timeout_rate");

export function record(res) {
  timeoutRate.add(res.error_code === 1050);
  return res;
}

export function isLiveChat() {
  return __ENV.CHAT_MODE === "live";
}

const WARMUP_S = 30;
const warmup = {
  executor: "constant-vus",
  vus: 5,
  duration: `${WARMUP_S}s`,
  exec: "default",
};

function mainStages() {
  const stages = [];
  for (const vus of [10, 25, 50, 100]) {
    stages.push({ duration: "15s", target: vus });
    stages.push({ duration: "90s", target: vus });
  }
  return stages;
}

// Seconds the `main` scenario runs, used by summary.js for rps.
// null means "use the whole test duration" (live chat has no fixed window).
export function mainSeconds() {
  if (isLiveChat()) return null;
  if (PROFILE === "ramp") return 4 * (15 + 90);
  if (PROFILE === "rate") return 180;
  return 30;
}

function scenarios(workload) {
  if (workload === "chatbot" && isLiveChat()) {
    return {
      main: { executor: "per-vu-iterations", vus: 1, iterations: 10, maxDuration: "10m" },
    };
  }
  switch (PROFILE) {
    case "smoke":
      return { main: { executor: "constant-vus", vus: 2, duration: "30s" } };
    case "ramp":
      return {
        warmup,
        main: {
          executor: "ramping-vus",
          startTime: `${WARMUP_S}s`,
          startVUs: 0,
          stages: mainStages(),
          gracefulRampDown: "10s",
        },
      };
    case "rate": {
      const rate = parseInt(__ENV.RATE || "0", 10);
      if (!rate) throw new Error("PROFILE=rate needs RATE=<requests per second>");
      return {
        warmup,
        main: {
          executor: "constant-arrival-rate",
          startTime: `${WARMUP_S}s`,
          rate,
          timeUnit: "1s",
          duration: "3m",
          preAllocatedVUs: 200,
          maxVUs: 500,
        },
      };
    }
    default:
      throw new Error(`unknown PROFILE ${PROFILE} (smoke|ramp|rate)`);
  }
}

// Thresholds that always pass. They exist so k6 emits {scenario:main}
// sub-metrics, which keeps warm-up traffic out of the reported numbers.
const MAIN = "{scenario:main}";

// extra.trends / extra.rates: custom metric names to expose for main too.
export function options(workload, extra = {}) {
  const th = {
    [`http_reqs${MAIN}`]: ["count>=0"],
    [`http_req_duration${MAIN}`]: ["max>=0"],
    [`http_req_failed${MAIN}`]: ["rate>=0"],
    [`checks${MAIN}`]: ["rate>=0"],
    [`timeout_rate${MAIN}`]: ["rate>=0"],
  };
  if (PROFILE === "rate") th[`dropped_iterations${MAIN}`] = ["count>=0"];
  for (const n of extra.trends || []) th[`${n}${MAIN}`] = ["max>=0"];
  for (const n of extra.rates || []) th[`${n}${MAIN}`] = ["rate>=0"];
  return {
    scenarios: scenarios(workload),
    thresholds: th,
    summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "p(99)", "max"],
  };
}
