// Animated scenes: intro, how-it-works diagrams, safeguards and outro.
import type { CSSProperties, ReactNode } from "react";
import { interpolate, Sequence, spring } from "remotion";
import { Backdrop, Check, ease, LiveDot, useInOut, useSceneFrame as useCurrentFrame } from "./components";
import { C, body, display } from "./theme";
import { FPS } from "./timeline";

function appear(f: number, at: number, len = 16) {
  return interpolate(f, [at, at + len], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease });
}

function Heading({ children, sub }: { children: ReactNode; sub?: string }) {
  const f = useCurrentFrame();
  const o = appear(f, 0, 18);
  return (
    <div style={{ position: "absolute", left: 140, top: 92, opacity: o, transform: `translateY(${(1 - o) * 14}px)` }}>
      <div style={{ fontFamily: display, fontWeight: 500, fontSize: 64, letterSpacing: "-0.025em" }}>{children}</div>
      {sub ? <div style={{ marginTop: 10, fontSize: 26, color: C.muted, fontWeight: 300 }}>{sub}</div> : null}
    </div>
  );
}

type NodeProps = { x: number; y: number; w: number; h: number; title: string; lines?: string[]; at: number; live?: boolean; dashed?: boolean; small?: boolean };
function Node({ x, y, w, h, title, lines = [], at, live, dashed, small }: NodeProps) {
  const f = useCurrentFrame();
  const o = appear(f, at);
  const style: CSSProperties = {
    position: "absolute",
    left: x,
    top: y,
    width: w,
    height: h,
    opacity: o,
    transform: `scale(${0.96 + 0.04 * o})`,
    border: `1px ${dashed ? "dashed" : "solid"} ${live ? C.live : C.line}`,
    borderRadius: 14,
    background: dashed ? "transparent" : C.card,
    padding: small ? "12px 16px" : "18px 22px",
    boxSizing: "border-box",
  };
  return (
    <div style={style}>
      <div style={{ fontFamily: display, fontWeight: 500, fontSize: small ? 24 : 30, letterSpacing: "-0.01em", display: "flex", alignItems: "center", gap: 10 }}>
        {live ? <LiveDot size={9} /> : null}
        {title}
      </div>
      {lines.map((l) => (
        <div key={l} style={{ fontSize: small ? 17 : 20, color: C.muted, marginTop: 6, lineHeight: 1.35 }}>
          {l}
        </div>
      ))}
    </div>
  );
}

type Pt = [number, number];
function Wire({ points, at, label, dashed = true }: { points: Pt[]; at: number; label?: string; dashed?: boolean }) {
  const f = useCurrentFrame();
  const p = appear(f, at, 20);
  const d = points.map((pt, i) => `${i ? "L" : "M"}${pt[0]},${pt[1]}`).join(" ");
  // Label at the middle of the middle segment, so it never lands inside a box.
  const i = Math.max(0, Math.floor((points.length - 2) / 2));
  const mid: Pt = [(points[i][0] + points[i + 1][0]) / 2 - 40, (points[i][1] + points[i + 1][1]) / 2];
  return (
    <>
      <path d={d} fill="none" stroke={C.muted} strokeOpacity={0.55} strokeWidth={1.6} strokeDasharray={dashed ? "6 7" : undefined} opacity={p} />
      {label ? (
        <text x={mid[0] + 10} y={mid[1] - 10} fill={C.muted} fontSize={17} fontFamily={body} opacity={p}>
          {label}
        </text>
      ) : null}
    </>
  );
}

/** A glowing dot that travels along a path of points between two frames. */
function Pulse({ points, from, to }: { points: Pt[]; from: number; to: number }) {
  const f = useCurrentFrame();
  if (f < from || f > to) return null;
  const t = interpolate(f, [from, to], [0, 1], { easing: ease });
  const lens = points.slice(1).map((pt, i) => Math.hypot(pt[0] - points[i][0], pt[1] - points[i][1]));
  const total = lens.reduce((a, b) => a + b, 0);
  let dist = t * total;
  let i = 0;
  while (i < lens.length - 1 && dist > lens[i]) dist -= lens[i++];
  const r = lens[i] ? dist / lens[i] : 0;
  const x = points[i][0] + (points[i + 1][0] - points[i][0]) * r;
  const y = points[i][1] + (points[i + 1][1] - points[i][1]) * r;
  return <circle cx={x} cy={y} r={9} fill={C.live} style={{ filter: `drop-shadow(0 0 10px ${C.live})` }} />;
}

// --- Intro ------------------------------------------------------------------------------
export function Intro({ duration }: { duration: number }) {
  const f = useCurrentFrame();
  const out = useInOut(duration, 14);
  const logo = spring({ frame: f - 6, fps: FPS, config: { damping: 14, mass: 0.7 } });
  const word = appear(f, 16, 20);
  const tag = appear(f, 34, 20);
  const stack = ["Mistral", "LangGraph", "FastAPI", "Pinecone", "Exa", "Next.js"];
  return (
    <Backdrop>
      <div style={{ position: "absolute", inset: 0, opacity: out, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 34 }}>
          <div style={{ width: 132, height: 132, borderRadius: 30, background: C.fg, display: "flex", alignItems: "center", justifyContent: "center", transform: `scale(${logo})` }}>
            <svg width="76" height="76" viewBox="0 0 24 24" fill="none" stroke={C.bg} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
              <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
            </svg>
          </div>
          <div style={{ fontFamily: display, fontWeight: 600, fontSize: 168, letterSpacing: "-0.03em", opacity: word, transform: `translateX(${(1 - word) * -20}px)` }}>Chat</div>
        </div>
        <div style={{ marginTop: 38, fontSize: 38, fontWeight: 300, color: C.muted, opacity: tag, textAlign: "center", maxWidth: 1250, lineHeight: 1.4 }}>
          Private AI chat that answers from your documents and the web, and cites every source.
        </div>
        <div style={{ display: "flex", gap: 14, marginTop: 46 }}>
          {stack.map((s, i) => (
            <div key={s} style={{ opacity: appear(f, 54 + i * 6, 14), border: `1px solid ${C.line}`, borderRadius: 4, padding: "8px 16px", fontSize: 22, color: C.fg }}>
              {s}
            </div>
          ))}
        </div>
      </div>
    </Backdrop>
  );
}

// --- Architecture -----------------------------------------------------------------------
export function Architecture({ duration }: { duration: number }) {
  const out = useInOut(duration, 14);
  const browser: Pt = [300, 560];
  const api: Pt = [800, 560];
  const agent: Pt = [800, 720];
  const mistral: Pt = [1390, 330];
  return (
    <Backdrop>
      <div style={{ position: "absolute", inset: 0, opacity: out }}>
        <Heading sub="One FastAPI app serves the frontend and the API; the agent calls the model and tools.">How it fits together</Heading>
        <svg width={1920} height={1080} style={{ position: "absolute", inset: 0 }}>
          <Wire points={[[400, 560], [560, 560]]} at={30} label="JSON + SSE" />
          <Wire points={[[800, 620], [800, 660]]} at={42} />
          <Wire points={[[1040, 720], [1170, 720], [1170, 330], [1250, 330]]} at={60} />
          <Wire points={[[1170, 470], [1250, 470]]} at={64} />
          <Wire points={[[1170, 610], [1250, 610]]} at={68} />
          <Wire points={[[1170, 750], [1250, 750]]} at={72} />
          <Wire points={[[700, 790], [700, 870]]} at={80} />
          <Wire points={[[900, 790], [900, 870]]} at={84} />
          <Wire points={[[1040, 520], [1120, 520], [1120, 900], [1250, 900]]} at={90} />
          <Pulse points={[browser, api, agent, [1170, 720], [1170, 330], mistral]} from={120} to={190} />
          <Pulse points={[mistral, [1170, 330], [1170, 720], agent, api, browser]} from={200} to={270} />
        </svg>
        <Node x={170} y={500} w={230} h={120} title="Browser" lines={["Next.js static export"]} at={10} />
        <Node x={560} y={290} w={480} h={500} title="FastAPI Cloud" lines={[]} at={18} dashed />
        <Node x={590} y={360} w={420} h={110} title="Frontend at /" lines={["Landing, sign in, chat, admin"]} at={24} small />
        <Node x={590} y={500} w={420} h={120} title="/api" lines={["Auth, chat, documents, admin", "Audit log on every request"]} at={30} small />
        <Node x={590} y={660} w={420} h={110} title="LangGraph agent" lines={["agent ⇄ tools → suggest"]} at={40} small live />
        <Node x={580} y={870} w={240} h={100} title="PostgreSQL" lines={["History, users, audit"]} at={80} small />
        <Node x={840} y={870} w={200} h={100} title="Redis" lines={["Context, limits"]} at={84} small />
        <Node x={1250} y={280} w={300} h={100} title="Mistral" lines={["ministral-14b, embeddings"]} at={60} small />
        <Node x={1250} y={420} w={300} h={100} title="Pinecone + Cohere" lines={["Document search"]} at={64} small />
        <Node x={1250} y={560} w={300} h={100} title="Exa" lines={["Web search"]} at={68} small />
        <Node x={1250} y={700} w={300} h={100} title="Open-Meteo" lines={["Weather"]} at={72} small />
        <Node x={1250} y={850} w={300} h={100} title="Jira + email" lines={["Approved bug reports"]} at={90} small />
      </div>
    </Backdrop>
  );
}

// --- Agent loop -------------------------------------------------------------------------
export function AgentLoop({ duration }: { duration: number }) {
  const f = useCurrentFrame();
  const out = useInOut(duration, 14);
  const tools = ["search_documents", "web_search", "get_weather", "report_bug"];
  const round = f < 150 ? 1 : f < 200 ? 2 : 2;
  return (
    <Backdrop>
      <div style={{ position: "absolute", inset: 0, opacity: out }}>
        <Heading sub="The model decides which tools to use, and can use several before it answers.">The agent loop</Heading>
        <svg width={1920} height={1080} style={{ position: "absolute", inset: 0 }}>
          <Wire points={[[300, 560], [430, 560]]} at={20} />
          <Wire points={[[730, 530], [1010, 530]]} at={30} label="tool calls" />
          <Wire points={[[1010, 600], [730, 600]]} at={36} label="results" />
          <Wire points={[[580, 640], [580, 800], [800, 800]]} at={44} label="answer" />
          <Wire points={[[1100, 800], [1300, 800]]} at={52} />
          <Pulse points={[[580, 560], [1160, 560]]} from={80} to={110} />
          <Pulse points={[[1160, 570], [580, 570]]} from={115} to={145} />
          <Pulse points={[[580, 560], [1160, 560]]} from={150} to={175} />
          <Pulse points={[[1160, 570], [580, 570]]} from={180} to={205} />
          <Pulse points={[[580, 640], [580, 800], [950, 800], [1360, 800]]} from={215} to={265} />
        </svg>
        <div style={{ position: "absolute", left: 230, top: 525, width: 70, height: 70, borderRadius: 70, border: `1px solid ${C.line}`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, color: C.muted, opacity: appear(f, 14) }}>
          start
        </div>
        <Node x={430} y={480} w={300} h={160} title="agent" lines={["Streams text,", "or asks for tools"]} at={14} live />
        <Node x={1010} y={480} w={360} h={160} title="tools" lines={["Run in parallel,", "citations numbered per turn"]} at={24} />
        <Node x={800} y={740} w={300} h={120} title="suggest" lines={["3 follow-up questions"]} at={48} />
        <div style={{ position: "absolute", left: 1300, top: 765, width: 70, height: 70, borderRadius: 70, border: `1px solid ${C.line}`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, color: C.muted, opacity: appear(f, 52) }}>
          end
        </div>
        <div style={{ position: "absolute", left: 1430, top: 470, display: "flex", flexDirection: "column", gap: 12 }}>
          {tools.map((t, i) => {
            const lit = (f > 85 && f < 110 && i < 2) || (f > 152 && f < 176 && i === 2);
            return (
              <div key={t} style={{ opacity: appear(f, 30 + i * 6), fontFamily: "ui-monospace, Menlo, monospace", fontSize: 21, padding: "8px 14px", borderRadius: 4, border: `1px solid ${lit ? C.live : C.line}`, color: lit ? C.live : C.fg }}>
                {t}
              </div>
            );
          })}
        </div>
        <div style={{ position: "absolute", left: 430, top: 900, fontSize: 24, color: C.muted, opacity: appear(f, 70) }}>
          Tool round {round} of at most 4, then the model must answer · failures go back to the model as results
        </div>
      </div>
    </Backdrop>
  );
}

// --- Memory -----------------------------------------------------------------------------
export function Memory({ duration }: { duration: number }) {
  const f = useCurrentFrame();
  const out = useInOut(duration, 14);
  const bars = 8;
  const evict = interpolate(f, [150, 210], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease });
  return (
    <Backdrop>
      <div style={{ position: "absolute", inset: 0, opacity: out }}>
        <Heading sub="The model sees a short working set; the full history is never lost.">Memory</Heading>
        <Node x={140} y={300} w={760} h={560} title="Redis · working set, 24 h" lines={["What the model sees each turn"]} at={12} live />
        <Node x={1020} y={300} w={760} h={560} title="PostgreSQL · full history" lines={["Every message, kept for good: text, sources, suggestions"]} at={22} />
        {/* Recent turns: the oldest pair slides into the summary when the window is full. */}
        <div style={{ position: "absolute", left: 180, top: 520, width: 680, opacity: appear(f, 30) }}>
          <div style={{ border: `1px dashed ${C.live}`, borderRadius: 10, padding: "14px 18px", fontSize: 21, color: C.live, marginBottom: 16, transform: `scale(${1 + 0.03 * Math.sin(evict * Math.PI)})` }}>
            Rolling summary {evict > 0.6 ? "(updated)" : ""}
          </div>
          {Array.from({ length: bars }).map((_, i) => {
            const leaving = i < 2 ? evict : 0;
            return (
              <div key={i} style={{ height: 22, marginBottom: 8, borderRadius: 4, width: i % 2 ? "78%" : "62%", marginLeft: i % 2 ? "22%" : 0, background: i % 2 ? C.raised : C.line, opacity: (1 - leaving) * appear(f, 36 + i * 4), transform: `translateY(${-leaving * 60}px)` }} />
            );
          })}
        </div>
        <div style={{ position: "absolute", left: 1060, top: 440, width: 680, opacity: appear(f, 40) }}>
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} style={{ height: 14, marginBottom: 7, borderRadius: 3, width: `${50 + ((i * 37) % 45)}%`, marginLeft: i % 2 ? "auto" : 0, background: C.line, opacity: appear(f, 44 + i * 3) }} />
          ))}
        </div>
        <div style={{ position: "absolute", left: 140, top: 890, width: 1640, fontSize: 24, color: C.muted, opacity: appear(f, 120), lineHeight: 1.5 }}>
          Over 100 messages, or over 80% of the input limit: the oldest turns are summarised and dropped, the last 4 turns are always kept. A cold cache is rebuilt from PostgreSQL.
        </div>
      </div>
    </Backdrop>
  );
}

// --- Safeguards -------------------------------------------------------------------------
export function Safeguards({ duration }: { duration: number }) {
  const f = useCurrentFrame();
  const out = useInOut(duration, 14);
  const items = [
    ["200 messages a day per user", "Checked before any model call"],
    ["30 web searches a day", "And at most 4 tool rounds per message"],
    ["Bug reports need an admin", "Nothing reaches Jira without approval"],
    ["Web pages are untrusted", "No bug reports after a web search; http(s) links only"],
    ["Login and sign-up limits", "Without locking out shared networks"],
    ["Instant revocation", "Logout and admin bans end sessions at once"],
  ];
  return (
    <Backdrop>
      <div style={{ position: "absolute", inset: 0, opacity: out }}>
        <Heading sub="Limits and checks that keep cost and risk bounded.">Safeguards</Heading>
        <div style={{ position: "absolute", left: 140, top: 330, display: "grid", gridTemplateColumns: "1fr 1fr", columnGap: 80, rowGap: 44, width: 1640 }}>
          {items.map(([t, d], i) => {
            const o = appear(f, 16 + i * 9);
            return (
              <div key={t} style={{ opacity: o, transform: `translateY(${(1 - o) * 12}px)`, display: "flex", gap: 20, borderTop: `1px dashed ${C.line}`, paddingTop: 26 }}>
                <Check size={30} />
                <div>
                  <div style={{ fontFamily: display, fontWeight: 500, fontSize: 36, letterSpacing: "-0.015em" }}>{t}</div>
                  <div style={{ fontSize: 23, color: C.muted, marginTop: 6 }}>{d}</div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </Backdrop>
  );
}

// --- Outro ------------------------------------------------------------------------------
export function Outro({ duration }: { duration: number }) {
  const f = useCurrentFrame();
  const out = useInOut(duration, 16);
  return (
    <Backdrop>
      <div style={{ position: "absolute", inset: 0, opacity: out, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <div style={{ fontFamily: display, fontWeight: 500, fontSize: 96, letterSpacing: "-0.03em", opacity: appear(f, 4) }}>Thanks for watching</div>
        <div style={{ marginTop: 26, fontSize: 32, color: C.muted, fontWeight: 300, opacity: appear(f, 18) }}>
          FastAPI · LangGraph · Mistral · Pinecone · Exa · Next.js
        </div>
        <Sequence from={30} layout="none">
          <div style={{ marginTop: 40, display: "flex", alignItems: "center", gap: 14, fontSize: 34, opacity: appear(f, 30) }}>
            <LiveDot />
            razin.tech
          </div>
        </Sequence>
      </div>
    </Backdrop>
  );
}
