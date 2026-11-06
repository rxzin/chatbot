"use client";

import { useEffect, useRef } from "react";

// Within this distance of the bottom counts as "at the bottom".
const PINNED_THRESHOLD_PX = 80;

/**
 * Keeps a scroll container at the bottom while the user is there.
 *
 * Scrolls when deps change (new or streaming messages) and when the container is
 * resized, e.g. when an error banner appears below it and shrinks it. If the user has
 * scrolled up to read, it leaves them where they are.
 */
export function useAutoScroll<T extends HTMLElement>(deps: unknown[]) {
  const containerRef = useRef<T | null>(null);
  const pinnedRef = useRef(true);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const onScroll = () => {
      const distance = container.scrollHeight - container.scrollTop - container.clientHeight;
      pinnedRef.current = distance <= PINNED_THRESHOLD_PX;
    };
    const observer = new ResizeObserver(() => {
      if (pinnedRef.current) container.scrollTop = container.scrollHeight;
    });

    container.addEventListener("scroll", onScroll, { passive: true });
    observer.observe(container);
    return () => {
      container.removeEventListener("scroll", onScroll);
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (container && pinnedRef.current) {
      container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return containerRef;
}
