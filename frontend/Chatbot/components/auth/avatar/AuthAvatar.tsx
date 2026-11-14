"use client";

import "@bible-strong/avatar-react/styles.css";
import { createAvatar } from "@bible-strong/avatar-react";
import { useTheme } from "next-themes";
import { authAvatarDefinition } from "./definition";
import type { AvatarTarget } from "./reactions";

// One character, two colourings: a grey cloud by day, a dark grey one by night. Both flush
// red while an error plays.
const LightAvatar = createAvatar(
  authAvatarDefinition({ body: "#d3d6dc", eyes: "#111316", alarm: "#f0696b" }),
);
const DarkAvatar = createAvatar(
  authAvatarDefinition({ body: "#3d424b", eyes: "#f4f5f7", alarm: "#cf3f43" }),
);

type AuthAvatarProps = {
  target: AvatarTarget;
  /** A reaction animation played to its end. */
  onAnimationEnd: () => void;
};

/** Client only: the avatar reads `window` when it renders. Load it with `ssr: false`. */
export default function AuthAvatar({ target, onAnimationEnd }: AuthAvatarProps) {
  const { resolvedTheme } = useTheme();
  const Themed = resolvedTheme === "light" ? LightAvatar : DarkAvatar;

  return (
    <Themed
      animation={target.animation}
      expression={target.expression}
      size="100%"
      ariaLabel="Assistant avatar reacting to the form"
      onAnimationEnd={onAnimationEnd}
    />
  );
}
