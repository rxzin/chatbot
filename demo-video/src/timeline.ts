// Turns the recorder's per-take timelines into a video's chapter plan: which slices of
// footage play, how fast, where to zoom and when to show captions. Two profiles share
// the footage: the full walkthrough and a fast highlight reel.
import admin from "./data/admin.json";
import landing from "./data/landing.json";
import mobile from "./data/mobile.json";
import user from "./data/user.json";
import weather from "./data/weather.json";

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;

type Box = { x: number; y: number; w: number; h: number };
type Event = {
  t: number;
  type: string;
  id?: string;
  title?: string;
  caption?: string;
  text?: string;
  label?: string;
  box?: Box;
  duration?: number;
  start?: number;
  firstToken?: number;
  end?: number;
};
type TakeData = {
  name: string;
  viewport: { width: number; height: number };
  duration: number;
  events: Event[];
};

const TAKES: Record<string, TakeData> = { landing, user, weather, admin, mobile } as Record<
  string,
  TakeData
>;

type ChapterOptions = {
  /** Base playback speed for this chapter. */
  rate?: number;
  /** Skip this many source seconds at the start (e.g. sign-in typing). */
  skip?: number;
  /** Stop after this many source seconds. */
  maxSeconds?: number;
};

type SceneId = "intro" | "architecture" | "agent" | "memory" | "safeguards" | "outro";

type Profile = {
  plan: [take: string, chapters: string[]][];
  options: Record<string, ChapterOptions>;
  /** Speeds while the model thinks and while it streams. */
  think: number;
  stream: number;
  /** Speed during logged key moments (zoom points); null leaves them at the base rate. */
  focusRate: number | null;
  /** Source seconds of each key moment that play at focusRate. */
  focusHold: number;
  titleSeconds: number;
  captionSeconds: number;
  speedBadge: boolean;
  before: { id: SceneId; seconds: number; speed: number }[];
  after: { id: SceneId; seconds: number; speed: number }[];
};

const FULL: Profile = {
  // The user take's weather chapter is replaced by the weather take.
  plan: [
    ["landing", ["landing", "use-cases"]],
    ["user", ["signin", "streaming", "documents", "web", "suggestions", "memory"]],
    ["weather", ["weather"]],
    ["user", ["bug", "voice"]],
    // Sign-in is shown once, for the user; admin and phone start already signed in.
    ["admin", ["admin-stats", "admin-bugs", "admin-audit", "admin-users"]],
    ["mobile", ["mobile"]],
  ],
  options: {
    "use-cases": { rate: 1.35 },
    signin: { rate: 1.7 },
    voice: { maxSeconds: 6 },
    "admin-users": { rate: 1.2 },
    mobile: { rate: 1.3, skip: 11 },
  },
  think: 4,
  stream: 2,
  focusRate: null,
  focusHold: 0,
  titleSeconds: 4.6,
  captionSeconds: 3.2,
  speedBadge: true,
  before: [{ id: "intro", seconds: 5.5, speed: 1 }],
  after: [
    { id: "architecture", seconds: 11, speed: 1 },
    { id: "agent", seconds: 10, speed: 1 },
    { id: "memory", seconds: 10, speed: 1 },
    { id: "safeguards", seconds: 8, speed: 1 },
    { id: "outro", seconds: 5.5, speed: 1 },
  ],
};

const HIGHLIGHTS: Profile = {
  plan: [
    ["landing", ["landing"]],
    ["user", ["signin", "documents", "web", "suggestions"]],
    ["weather", ["weather"]],
    ["user", ["bug"]],
    ["admin", ["admin-bugs", "admin-audit"]],
    ["mobile", ["mobile"]],
  ],
  options: {
    landing: { rate: 2.6, maxSeconds: 8 },
    signin: { rate: 3.4 },
    documents: { rate: 3.8 },
    web: { rate: 3.4 },
    suggestions: { rate: 3.2 },
    weather: { rate: 3.2 },
    bug: { rate: 3.2, maxSeconds: 13 },
    "admin-bugs": { rate: 3.6 },
    "admin-audit": { rate: 3 },
    mobile: { rate: 3, skip: 11, maxSeconds: 12 },
  },
  think: 10,
  stream: 5,
  focusRate: 1.5,
  focusHold: 1.9,
  titleSeconds: 2,
  captionSeconds: 1.8,
  speedBadge: false,
  before: [{ id: "intro", seconds: 2.3, speed: 2.4 }],
  after: [
    { id: "agent", seconds: 4, speed: 2.6 },
    { id: "outro", seconds: 2.3, speed: 2.4 },
  ],
};

export type Segment = { srcStart: number; srcEnd: number; rate: number; from: number; dur: number; wait: boolean };
export type Overlay = { from: number; dur: number };
export type Focus = Overlay & { box: Box };
export type Caption = Overlay & { text: string };

export type FootageChapter = {
  kind: "footage";
  id: string;
  title: string;
  caption: string;
  take: string;
  viewport: { width: number; height: number };
  from: number;
  duration: number;
  titleFrames: number;
  speedBadge: boolean;
  segments: Segment[];
  focuses: Focus[];
  captions: Caption[];
};

export type SceneChapter = {
  kind: "scene";
  id: SceneId;
  title: string;
  from: number;
  duration: number;
  speed: number;
};

export type Chapter = FootageChapter | SceneChapter;

const SCENE_TITLES: Record<SceneId, string> = {
  intro: "Chat",
  architecture: "How it fits together",
  agent: "The agent loop",
  memory: "Memory",
  safeguards: "Safeguards",
  outro: "Thanks",
};

function footageChapter(profile: Profile, takeName: string, id: string): Omit<FootageChapter, "from"> {
  const take = TAKES[takeName];
  const chapters = take.events.filter((e) => e.type === "chapter");
  const index = chapters.findIndex((e) => e.id === id);
  if (index < 0) throw new Error(`No chapter ${id} in ${takeName}`);
  const ev = chapters[index];
  const opt = profile.options[id] ?? {};
  const base = opt.rate ?? 1;
  const start = ev.t + (opt.skip ?? 0);
  const natural = index + 1 < chapters.length ? chapters[index + 1].t : take.duration - 0.2;
  const end = opt.maxSeconds ? Math.min(natural, start + opt.maxSeconds) : natural;
  const inRange = (e: Event) => e.t >= start && e.t < end;

  // Windows with their own speed. The first matching kind wins: key moments, then
  // model thinking, then streaming; everything else plays at the base rate.
  type Win = { a: number; b: number; rate: number; wait: boolean };
  const focusWins: Win[] =
    profile.focusRate === null
      ? []
      : take.events
          .filter((e) => e.type === "focus" && inRange(e))
          .map((e) => ({ a: e.t, b: e.t + Math.min(e.duration ?? 2.5, profile.focusHold), rate: profile.focusRate!, wait: false }));
  const waits = take.events.filter((e) => e.type === "wait" && (e.end ?? 0) > start && (e.start ?? 0) < end);
  const thinkWins: Win[] = [];
  const streamWins: Win[] = [];
  for (const w of waits) {
    const [think, stream] =
      w.label === "indexing" || w.label === "jira" ? [profile.think, profile.think] : [profile.think, profile.stream];
    const ws = w.start ?? start;
    const wf = Math.max(w.firstToken ?? ws, ws);
    thinkWins.push({ a: ws, b: wf, rate: think, wait: true });
    streamWins.push({ a: wf, b: w.end ?? wf, rate: stream, wait: true });
  }
  const layers = [focusWins, thinkWins, streamWins];

  const cuts = new Set<number>([start, end]);
  for (const layer of layers) for (const w of layer) for (const x of [w.a, w.b]) if (x > start && x < end) cuts.add(x);
  const points = [...cuts].sort((a, b) => a - b);

  const segments: Segment[] = [];
  let outFrame = 0;
  for (let i = 0; i + 1 < points.length; i++) {
    const a = points[i];
    const b = points[i + 1];
    if (b - a < 0.05) continue;
    const mid = (a + b) / 2;
    let rate = base;
    let wait = false;
    for (const layer of layers) {
      const hit = layer.find((w) => mid >= w.a && mid < w.b);
      if (hit) {
        rate = hit.rate;
        wait = hit.wait;
        break;
      }
    }
    const last = segments[segments.length - 1];
    if (last && last.rate === rate && last.wait === wait && Math.abs(last.srcEnd - a) < 1e-6) {
      // Merge with the previous slice when nothing changes.
      outFrame -= last.dur;
      last.srcEnd = b;
      last.dur = Math.max(1, Math.round(((b - last.srcStart) / rate) * FPS));
      outFrame += last.dur;
      continue;
    }
    const dur = Math.max(1, Math.round(((b - a) / rate) * FPS));
    segments.push({ srcStart: a, srcEnd: b, rate, from: outFrame, dur, wait });
    outFrame += dur;
  }

  const toOut = (t: number) => {
    for (const s of segments) {
      if (t >= s.srcStart && t <= s.srcEnd) return s.from + ((t - s.srcStart) / s.rate) * FPS;
    }
    return t < start ? 0 : outFrame;
  };
  const clampDur = (from: number, seconds: number) => Math.max(1, Math.min(Math.round(seconds * FPS), outFrame - from));

  return {
    kind: "footage",
    id,
    title: ev.title ?? id,
    caption: ev.caption ?? "",
    take: takeName,
    viewport: take.viewport,
    duration: outFrame,
    titleFrames: Math.round(profile.titleSeconds * FPS),
    speedBadge: profile.speedBadge,
    segments,
    focuses: take.events
      .filter((e) => e.type === "focus" && e.box && inRange(e))
      .map((e) => {
        const from = Math.round(toOut(e.t));
        const seconds = profile.focusRate === null ? e.duration ?? 2.5 : Math.min(e.duration ?? 2.5, profile.focusHold) / profile.focusRate + 0.3;
        return { from, dur: clampDur(from, seconds), box: e.box! };
      })
      .filter((f) => f.dur > 30),
    captions: take.events
      .filter((e) => e.type === "caption" && inRange(e))
      .map((e) => {
        const from = Math.round(toOut(e.t));
        return { from, dur: clampDur(from, profile.captionSeconds), text: e.text ?? "" };
      })
      .filter((c) => c.dur > 20),
  };
}

function build(profile: Profile): { chapters: Chapter[]; total: number } {
  const scene = (s: Profile["before"][number]): Omit<SceneChapter, "from"> => ({
    kind: "scene",
    id: s.id,
    title: SCENE_TITLES[s.id],
    duration: Math.round(s.seconds * FPS),
    speed: s.speed,
  });
  const parts: Omit<Chapter, "from">[] = profile.before.map(scene);
  for (const [take, ids] of profile.plan) for (const id of ids) parts.push(footageChapter(profile, take, id));
  parts.push(...profile.after.map(scene));

  let from = 0;
  const chapters = parts.map((p) => {
    const c = { ...p, from } as Chapter;
    from += p.duration;
    return c;
  });
  return { chapters, total: from };
}

export const TIMELINE = build(FULL);
export const HIGHLIGHTS_TIMELINE = build(HIGHLIGHTS);
export type Timeline = typeof TIMELINE;
