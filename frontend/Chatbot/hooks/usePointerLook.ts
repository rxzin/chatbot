"use client";

import { useEffect, useRef, useState, type RefObject } from "react";

/** A gaze: right and up, each from -1 to 1. */
export type Look = readonly [number, number];

/** Keeps a gaze inside a circle, so the eyes can't slide off a round face. */
export function capLook(x: number, y: number, limit: number): Look {
  const length = Math.hypot(x, y);
  if (length <= limit || length === 0) return [x, y];
  return [(x / length) * limit, (y / length) * limit];
}

/** The gaze that points from the middle of `anchor` toward the middle of `target`. */
export function lookToward(anchor: Element, target: Element, limit: number): Look {
  const from = anchor.getBoundingClientRect();
  const to = target.getBoundingClientRect();
  const dx = to.left + to.width / 2 - (from.left + from.width / 2);
  const dy = to.top + to.height / 2 - (from.top + from.height / 2);
  // Fields sit far to one side, so the vertical offset is scaled up or every field would
  // read as the same sideways glance.
  return capLook(dx / (from.width * 1.5), -dy / (from.height * 0.6), limit);
}

type PointerLookOptions = {
  /** A gaze is capped to a circle of this radius. */
  limit?: number;
  /** Positions per axis the gaze snaps to. Match the avatar's grid of looking expressions. */
  steps?: number;
  /** With the cursor still for this long, the gaze is dropped (null). */
  restAfterMs?: number;
  /** The least time between two changes of gaze, so a sweep is a few moves, not dozens. */
  minIntervalMs?: number;
};

/**
 * Follows the cursor anywhere on the page and returns a capped gaze for the element in
 * `anchor`, snapped to a grid. The avatar eases between positions itself, so this hook's
 * job is to change position rarely and decisively: a position is sticky, and only gives
 * way once the cursor is clearly nearer another one. That is what stops the avatar
 * trembling when the cursor sits on the line between two positions.
 *
 * Returns null while `active` is false, before the cursor first moves, and at rest.
 */
export function usePointerLook(
  anchor: RefObject<Element | null>,
  active: boolean,
  { limit = 1, steps = 7, restAfterMs = 2600, minIntervalMs = 110 }: PointerLookOptions = {},
): Look | null {
  const [look, setLook] = useState<Look | null>(null);
  // The grid cell the gaze is in. Kept across pauses so the stickiness carries over.
  const cell = useRef<[number, number]>([(steps - 1) / 2, (steps - 1) / 2]);

  useEffect(() => {
    if (!active) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const middle = (steps - 1) / 2;
    let rest = 0;
    let pending = 0;
    let changedAt = 0;
    let latest: Look = [0, 0];

    // A cell is kept until the gaze is more than 0.7 of a cell from its centre: past the
    // halfway line, so two neighbours can't trade places on a small wobble.
    const snap = (value: number, held: number) => {
      const exact = (value + 1) * middle;
      return Math.abs(exact - held) > 0.7 ? Math.round(exact) : held;
    };

    const apply = () => {
      pending = 0;
      const [column, row] = cell.current;
      const next: [number, number] = [snap(latest[0], column), snap(latest[1], row)];
      if (next[0] !== column || next[1] !== row) changedAt = performance.now();
      cell.current = next;
      const snapped: Look = [next[0] / middle - 1, next[1] / middle - 1];
      setLook((before) =>
        before && before[0] === snapped[0] && before[1] === snapped[1] ? before : snapped,
      );
    };

    const onMove = (event: PointerEvent) => {
      const box = anchor.current?.getBoundingClientRect();
      if (!box || box.width === 0) return;
      // One and a half avatar widths away is as far as the gaze goes.
      const reach = box.width * 1.5;
      latest = capLook(
        (event.clientX - (box.left + box.width / 2)) / reach,
        -(event.clientY - (box.top + box.height / 2)) / reach,
        limit,
      );
      window.clearTimeout(rest);
      rest = window.setTimeout(() => setLook(null), restAfterMs);
      if (pending) return;
      const wait = Math.max(0, minIntervalMs - (performance.now() - changedAt));
      pending = window.setTimeout(apply, wait);
    };

    window.addEventListener("pointermove", onMove, { passive: true });
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.clearTimeout(rest);
      window.clearTimeout(pending);
    };
  }, [active, anchor, limit, steps, restAfterMs, minIntervalMs]);

  return active ? look : null;
}
