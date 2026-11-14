import type { Look } from "@/hooks/usePointerLook";
import cloudee from "./cloudee.avatar.json";

/**
 * The auth avatar's own vocabulary, written for @bible-strong/avatar-react 0.2: named
 * expressions, and animations that are sequences of them. The body is Cloudee, from the
 * Avatar Lab's default library; every expression below is ours.
 */

type Eye = { width: number; height: number; x: number; y: number; angle: number };
type Expression = {
  head: { x: number; y: number; z: number };
  position?: { x: number; y: number; z: number };
  eyes: { left: Eye; right: Eye; spacing: number };
  perspective: number;
  blinking?: boolean;
  motion: { eyes: "none" | "microSaccades" | "shake"; body: "none" | "slowDrift" | "shake" };
  colors?: { body: string };
};
type Step = {
  expression: string;
  holdMs: number;
  transitionMs: number;
  transition: "spring" | "smooth" | "snappy";
};

export type AvatarColors = {
  body: string;
  eyes: string;
  /** The body while an error plays. */
  alarm: string;
};

/** Looking positions per axis. Odd, so the middle one faces straight ahead. */
export const LOOK_STEPS = 7;
const GRID = LOOK_STEPS;
const MIDDLE = (GRID - 1) / 2;
/** The furthest the head turns, in degrees. This is what keeps the eyes on the face. */
const MAX_YAW = 28;
const MAX_PITCH = 18;

const STILL: Expression["motion"] = { eyes: "none", body: "none" };
const ALIVE: Expression["motion"] = { eyes: "microSaccades", body: "slowDrift" };
const FLOATING: Expression["motion"] = { eyes: "none", body: "slowDrift" };

/** Cloudee's own eyes: two tall pills, close together. */
const GAP = 24;
const eye = (width = 14, height = 45, x = 0, y = -1, angle = 0): Eye => ({
  width,
  height,
  x,
  y,
  angle,
});

const expression = (
  head: [pitch: number, yaw: number, roll: number],
  left: Eye,
  right: Eye,
  spacing: number,
  rest: Partial<Expression> = {},
): Expression => ({
  head: { x: head[0], y: head[1], z: head[2] },
  eyes: { left, right, spacing },
  perspective: 1,
  blinking: true,
  motion: STILL,
  ...rest,
});

/** Following the cursor: the head turns most of the way and the eyes lean the rest. */
function looking(right: number, up: number): Expression {
  const open = eye(14, 45, right * 4, -1 - up * 8);
  // Held still: any ambient motion here reads as a tremble while the cursor moves.
  return expression([up * MAX_PITCH, right * MAX_YAW, right * -3], open, open, GAP);
}

/** Watching a field: the same turn, with the eyes splayed in curiosity and a tilted head. */
function watching(right: number, up: number): Expression {
  const y = -2 - up * 8;
  return expression(
    [up * MAX_PITCH, right * MAX_YAW, right * -7],
    eye(15, 42, right * 4, y, 22),
    eye(15, 42, right * 4, y, -22),
    42,
    { motion: FLOATING },
  );
}

const cellKey = (kind: "look" | "watch", column: number, row: number) =>
  `${kind}-${column}-${row}`;

/** The name of the expression nearest a gaze: following the cursor, or watching a field. */
export function lookExpression([right, up]: Look, kind: "look" | "watch"): string {
  const cell = (value: number) => Math.round((Math.min(1, Math.max(-1, value)) + 1) * MIDDLE);
  return cellKey(kind, cell(right), cell(up));
}

function expressions(alarm: string): Record<string, Expression> {
  const red = { colors: { body: alarm }, blinking: false };
  const all: Record<string, Expression> = {
    neutral: expression([0, 0, 0], eye(), eye(), GAP),
    // Idle: two easy poses to float between.
    "rest-left": expression([3, -8, -4], eye(), eye(), GAP, { motion: ALIVE }),
    "rest-right": expression([-2, 7, 4], eye(14, 43), eye(14, 43), GAP, { motion: ALIVE }),
    // Password: eyes shut tight, head turned down and away from the form.
    hiding: expression([-15, -24, -8], eye(30, 5, 0, 4), eye(30, 5, 0, 4), 46, {
      blinking: false,
    }),
    // Error: the body flushes red, the eyes pinch into a frown, and it shakes.
    alarm: expression([-4, 0, 7], eye(17, 30, 0, 2, -30), eye(17, 30, 0, 2, 30), 46, {
      ...red,
      motion: { eyes: "none", body: "shake" },
    }),
    sorry: expression([-10, 5, 4], eye(16, 30, 0, 6, -18), eye(16, 30, 0, 6, 18), 40, red),
    // Success: wide eyes and a hop from side to side.
    "joy-left": expression([8, -13, -10], eye(18, 54, 0, -6), eye(18, 54, 0, -6), 32, {
      position: { x: 0, y: -16, z: 0 },
    }),
    "joy-right": expression([8, 13, 10], eye(18, 54, 0, -6), eye(18, 54, 0, -6), 32, {
      position: { x: 0, y: -8, z: 0 },
    }),
    joy: expression([5, 0, 0], eye(17, 50, 0, -5), eye(17, 50, 0, -5), 30),
  };
  for (let column = 0; column < GRID; column += 1) {
    for (let row = 0; row < GRID; row += 1) {
      const right = (column - MIDDLE) / MIDDLE;
      const up = (row - MIDDLE) / MIDDLE;
      all[cellKey("look", column, row)] = looking(right, up);
      all[cellKey("watch", column, row)] = watching(right, up);
    }
  }
  return all;
}

const step = (
  name: string,
  holdMs: number,
  transitionMs: number,
  transition: Step["transition"] = "smooth",
): Step => ({ expression: name, holdMs, transitionMs, transition });

const blink = (enabled: boolean) => ({
  enabled,
  initialDelayMs: 1800,
  minIntervalMs: 2800,
  maxIntervalMs: 5600,
  durationMs: 260,
});

const animations = {
  idle: {
    playbackMode: "loop" as const,
    steps: [step("rest-left", 4200, 1100), step("rest-right", 4200, 1100)],
    blink: blink(true),
  },
  error: {
    playbackMode: "once" as const,
    steps: [step("alarm", 900, 180, "snappy"), step("sorry", 650, 380)],
    blink: blink(false),
  },
  success: {
    playbackMode: "once" as const,
    steps: [
      step("joy-left", 260, 260, "spring"),
      step("joy-right", 260, 320, "spring"),
      step("joy", 800, 320, "spring"),
    ],
    blink: blink(false),
  },
};

export type AvatarAnimation = keyof typeof animations;

/** The whole avatar file for one colouring, in the shape `createAvatar` reads. */
export function authAvatarDefinition({ body, eyes, alarm }: AvatarColors) {
  const all = expressions(alarm);
  return {
    schema: "bible-strong/avatar-definition",
    schemaVersion: 1,
    name: cloudee.name,
    body: cloudee.body,
    colors: { body, eyes },
    expressions: all,
    expressionOrder: Object.keys(all),
    animations,
    animationOrder: Object.keys(animations),
  };
}
