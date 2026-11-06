import { createContext, useContext, type CSSProperties, type ReactNode } from "react";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  OffthreadVideo,
  Sequence,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { C, body, display } from "./theme";
import type { Chapter, FootageChapter } from "./timeline";
import { FPS, HEIGHT, WIDTH } from "./timeline";

const ease = Easing.bezier(0.16, 1, 0.3, 1);

/** Animated scenes can play faster: they read this frame instead of the real one. */
export const SceneSpeed = createContext(1);
export function useSceneFrame() {
  return useCurrentFrame() * useContext(SceneSpeed);
}

/** Fades a value in over the first frames and out over the last. */
export function useInOut(duration: number, edge = 12) {
  const f = useCurrentFrame();
  // Short items get shorter fades, so the input range always increases.
  const e = Math.max(1, Math.min(edge, Math.floor((duration - 1) / 2)));
  return interpolate(f, [0, e, duration - e, duration], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: ease,
  });
}

/** Black ground with the landing page's dashed rails. */
export function Backdrop({ children }: { children?: ReactNode }) {
  const rail: CSSProperties = {
    position: "absolute",
    top: 0,
    bottom: 0,
    width: 0,
    borderLeft: `1px dashed ${C.line}`,
  };
  return (
    <AbsoluteFill style={{ background: C.bg, fontFamily: body, color: C.fg }}>
      <div style={{ ...rail, left: 64 }} />
      <div style={{ ...rail, right: 64 }} />
      {children}
    </AbsoluteFill>
  );
}

export function LiveDot({ size = 10 }: { size?: number }) {
  const f = useCurrentFrame();
  const pulse = 0.55 + 0.45 * Math.sin((f / FPS) * Math.PI * 1.6);
  return (
    <span
      style={{
        display: "inline-block",
        width: size,
        height: size,
        borderRadius: size,
        background: C.live,
        opacity: 0.6 + 0.4 * pulse,
        boxShadow: `0 0 ${8 * pulse}px ${C.live}`,
      }}
    />
  );
}

/** Chapter title, bottom left, for the first seconds of a chapter. */
export function LowerThird({ title, caption, duration, frames }: { title: string; caption: string; duration: number; frames: number }) {
  const f = useCurrentFrame();
  const shown = Math.min(duration, frames);
  const e = Math.max(1, Math.min(14, Math.floor((shown - 1) / 2)));
  const o = interpolate(f, [0, e, shown - e, shown], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: ease,
  });
  const y = interpolate(o, [0, 1], [24, 0]);
  return (
    <div
      style={{
        position: "absolute",
        left: 120,
        bottom: 96,
        opacity: o,
        transform: `translateY(${y}px)`,
        background: "rgba(9,9,11,0.88)",
        border: `1px solid ${C.line}`,
        borderRadius: 14,
        padding: "22px 30px",
        backdropFilter: "blur(8px)",
        maxWidth: 820,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <LiveDot />
        <span style={{ fontFamily: display, fontWeight: 500, fontSize: 44, letterSpacing: "-0.02em" }}>{title}</span>
      </div>
      {caption ? (
        <div style={{ marginTop: 8, marginLeft: 24, fontSize: 24, color: C.muted, fontWeight: 300 }}>{caption}</div>
      ) : null}
    </div>
  );
}

export function CaptionPill({ text, duration }: { text: string; duration: number }) {
  const o = useInOut(duration, 10);
  return (
    <div
      style={{
        position: "absolute",
        left: "50%",
        top: 88,
        transform: `translate(-50%, ${interpolate(o, [0, 1], [-10, 0])}px)`,
        opacity: o,
        background: "rgba(9,9,11,0.9)",
        border: `1px solid ${C.line}`,
        borderRadius: 999,
        padding: "12px 26px",
        fontSize: 26,
        display: "flex",
        alignItems: "center",
        gap: 12,
        whiteSpace: "nowrap",
      }}
    >
      <LiveDot size={8} />
      {text}
    </div>
  );
}

/** Thin progress bar along the bottom, ticked at each chapter. */
export function ProgressBar({ chapters, total }: { chapters: Chapter[]; total: number }) {
  const f = useCurrentFrame();
  const width = WIDTH - 128;
  return (
    <div style={{ position: "absolute", left: 64, right: 64, bottom: 36, height: 3, background: C.line }}>
      <div style={{ height: 3, width: (f / total) * width, background: C.live }} />
      {chapters.slice(1).map((c) => (
        <div
          key={c.id + c.from}
          style={{ position: "absolute", left: (c.from / total) * width, top: -3, width: 1, height: 9, background: C.muted, opacity: 0.5 }}
        />
      ))}
    </div>
  );
}

/** Where the footage sits on the 1920x1080 canvas. */
function frameFor(chapter: FootageChapter) {
  const { width, height } = chapter.viewport;
  if (height > width) {
    // Phone footage: a tall frame, centred.
    const h = 900;
    const w = Math.round((width / height) * h);
    return { x: Math.round((WIDTH - w) / 2), y: 72, w, h, phone: true };
  }
  const w = 1680;
  const h = Math.round((height / width) * w);
  return { x: Math.round((WIDTH - w) / 2), y: Math.round((HEIGHT - h) / 2) - 8, w, h, phone: false };
}

export function FootageScene({ chapter }: { chapter: FootageChapter }) {
  const f = useCurrentFrame();
  const frame = frameFor(chapter);
  const k = frame.w / chapter.viewport.width;

  // Zoom towards the active focus box, easing in and out.
  let s = 1;
  let tx = 0;
  let ty = 0;
  if (!frame.phone) {
    for (const fo of chapter.focuses) {
      if (f < fo.from || f > fo.from + fo.dur) continue;
      const target = Math.min(1.55, Math.min((frame.w * 0.62) / (fo.box.w * k), (frame.h * 0.62) / (fo.box.h * k)));
      if (target < 1.1) continue;
      const p = interpolate(f, [fo.from, fo.from + 14, fo.from + fo.dur - 14, fo.from + fo.dur], [0, 1, 1, 0], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
        easing: ease,
      });
      const cx = (fo.box.x + fo.box.w / 2) * k;
      const cy = (fo.box.y + fo.box.h / 2) * k;
      const z = 1 + (target - 1) * p;
      const clampX = (v: number) => Math.min(0, Math.max(frame.w - frame.w * z, v));
      const clampY = (v: number) => Math.min(0, Math.max(frame.h - frame.h * z, v));
      s = z;
      tx = clampX(frame.w / 2 - cx * z) * p + 0 * (1 - p);
      ty = clampY(frame.h / 2 - cy * z) * p;
      break;
    }
  }

  const src = staticFile(`footage/${chapter.take}.webm`);
  const intro = spring({ frame: f, fps: FPS, config: { damping: 200 }, durationInFrames: 18 });

  return (
    <Backdrop>
      <div
        style={{
          position: "absolute",
          left: frame.x,
          top: frame.y,
          width: frame.w,
          height: frame.h,
          borderRadius: frame.phone ? 36 : 14,
          border: `1px solid ${C.line}`,
          overflow: "hidden",
          background: C.card,
          opacity: intro,
          transform: `scale(${0.985 + 0.015 * intro})`,
          boxShadow: frame.phone ? `0 0 0 10px ${C.raised}` : undefined,
        }}
      >
        <div style={{ width: frame.w, height: frame.h, transformOrigin: "0 0", transform: `translate(${tx}px, ${ty}px) scale(${s})` }}>
          {chapter.segments.map((seg, i) => (
            <Sequence key={i} from={seg.from} durationInFrames={seg.dur} layout="none">
              <OffthreadVideo
                src={src}
                muted
                trimBefore={Math.round(seg.srcStart * FPS)}
                playbackRate={seg.rate}
                style={{ width: frame.w, height: frame.h, display: "block" }}
              />
            </Sequence>
          ))}
        </div>
      </div>

      {chapter.segments
        .filter((seg) => chapter.speedBadge && seg.wait && seg.dur > 8)
        .map((seg, i) => (
          <Sequence key={`speed-${i}`} from={seg.from} durationInFrames={seg.dur} layout="none">
            <SpeedBadge rate={seg.rate} duration={seg.dur} />
          </Sequence>
        ))}

      {chapter.captions.map((c, i) => (
        <Sequence key={`cap-${i}`} from={c.from} durationInFrames={c.dur} layout="none">
          <CaptionPill text={c.text} duration={c.dur} />
        </Sequence>
      ))}

      {frame.phone ? <PhoneNotes duration={chapter.duration} /> : null}
      <LowerThird title={chapter.title} caption={chapter.caption} duration={chapter.duration} frames={chapter.titleFrames} />
    </Backdrop>
  );
}

function SpeedBadge({ rate, duration }: { rate: number; duration: number }) {
  const o = useInOut(duration, 6);
  return (
    <div
      style={{
        position: "absolute",
        right: 140,
        top: 60,
        opacity: o * 0.9,
        fontSize: 20,
        color: C.muted,
        border: `1px solid ${C.line}`,
        borderRadius: 4,
        padding: "6px 12px",
        background: "rgba(9,9,11,0.85)",
      }}
    >
      Waiting for the model · {rate}× speed
    </div>
  );
}

function PhoneNotes({ duration }: { duration: number }) {
  const o = useInOut(duration, 18);
  const items = ["Conversations slide in from the side", "Documents open in a panel", "Same streaming chat and citations"];
  return (
    <div style={{ position: "absolute", left: 1290, top: 360, opacity: o, width: 520 }}>
      {items.map((t, i) => (
        <Sequence key={t} from={20 + i * 22} layout="none">
          <FadeLine text={t} />
        </Sequence>
      ))}
    </div>
  );
}

function FadeLine({ text }: { text: string }) {
  const f = useCurrentFrame();
  const o = interpolate(f, [0, 14], [0, 1], { extrapolateRight: "clamp", easing: ease });
  return (
    <div style={{ opacity: o, transform: `translateX(${(1 - o) * 16}px)`, display: "flex", gap: 14, alignItems: "center", fontSize: 28, marginBottom: 22, color: C.fg }}>
      <Check size={26} />
      {text}
    </div>
  );
}

/** A drawn check mark in the live colour. */
export function Check({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={C.live} strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
      <path d="M5 12.5l4.5 4.5L19 7" />
    </svg>
  );
}

export { ease, useVideoConfig };
