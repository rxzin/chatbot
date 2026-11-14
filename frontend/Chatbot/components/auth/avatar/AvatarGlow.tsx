"use client";

import { motion, useReducedMotion } from "motion/react";

const pool = (color: string) =>
  `radial-gradient(closest-side, color-mix(in oklab, ${color} 70%, transparent) 0%, color-mix(in oklab, ${color} 46%, transparent) 40%, color-mix(in oklab, ${color} 14%, transparent) 62%, transparent 80%)`;

const layer = "pointer-events-none absolute -inset-[45%] rounded-full";

/**
 * A soft pool of light behind the avatar. It breathes slowly while idle, flares in the
 * live colour on success, and flushes red with the avatar on an error.
 */
export function AvatarGlow({ reaction }: { reaction: "error" | "success" | null }) {
  const reduceMotion = useReducedMotion();
  const flare = { duration: 0.35, ease: "easeOut" as const };

  return (
    <>
      <motion.div
        aria-hidden
        className={layer}
        style={{ background: pool("#ffffff") }}
        initial={{ opacity: 0.4, scale: 1 }}
        animate={
          reaction
            ? { opacity: 0.15, scale: 1 }
            : reduceMotion
              ? { opacity: 0.5, scale: 1 }
              : { opacity: [0.3, 0.62, 0.3], scale: [0.96, 1.06, 0.96] }
        }
        transition={
          reaction || reduceMotion
            ? flare
            : { duration: 5.5, ease: "easeInOut", repeat: Infinity }
        }
      />
      <motion.div
        aria-hidden
        className={layer}
        style={{ background: pool("var(--live)") }}
        initial={{ opacity: 0, scale: 1 }}
        animate={reaction === "success" ? { opacity: 0.9, scale: 1.15 } : { opacity: 0, scale: 1 }}
        transition={flare}
      />
      <motion.div
        aria-hidden
        className={layer}
        style={{ background: pool("#ef4444") }}
        initial={{ opacity: 0, scale: 1 }}
        animate={reaction === "error" ? { opacity: 0.85, scale: 1.1 } : { opacity: 0, scale: 1 }}
        transition={flare}
      />
    </>
  );
}
