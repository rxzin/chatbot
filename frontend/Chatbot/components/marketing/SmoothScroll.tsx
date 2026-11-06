"use client";

import Lenis from "lenis";
import { useEffect } from "react";

/**
 * Lenis smooth scrolling for the marketing page.
 *
 * - Honours prefers-reduced-motion (Lenis's default): scrolling then tracks the input
 *   1:1 and jumps are instant.
 * - Handles in-page links like #features, including from the mobile menu, which is
 *   why anchor scrolls are forced: the menu's scroll lock is still on when they start.
 * - Pauses while a Radix dialog or sheet locks scrolling, so the page behind doesn't
 *   move. Elements marked data-lenis-prevent keep their own native scrolling.
 */
export function SmoothScroll() {
  useEffect(() => {
    const lenis = new Lenis({
      autoRaf: true,
      lerp: 0.1,
      anchors: { force: true },
      allowNestedScroll: true,
      stopInertiaOnNavigate: true,
    });

    const syncWithScrollLock = () => {
      if (document.body.hasAttribute("data-scroll-locked")) lenis.stop();
      else lenis.start();
    };
    const observer = new MutationObserver(syncWithScrollLock);
    observer.observe(document.body, {
      attributes: true,
      attributeFilter: ["data-scroll-locked"],
    });

    return () => {
      observer.disconnect();
      lenis.destroy();
    };
  }, []);

  return null;
}
