"use client";

import { Pause, Play } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { RailSection, SectionHeading } from "./Frame";

/**
 * Playback speed of the looping demo. The reel is cut fast, so a little under 1 makes it
 * easier to follow: 1 is as rendered, 0.8 is 80% speed. Below about 0.6 the sped-up
 * screen footage starts to look choppy; re-render a slower cut instead (demo-video/).
 */
export const DEMO_PLAYBACK_RATE = 0.85;

const SRC = "/demo/chat-demo.mp4";
const POSTER = "/demo/chat-demo-poster.jpg";

/**
 * The product demo, looping like a moving screenshot. It plays only while on screen,
 * and doesn't autoplay for people who prefer reduced motion. The pause button is there
 * because it runs for more than five seconds.
 */
export function DemoVideo() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  // Set by the visitor: once they pause, scrolling back into view doesn't resume it.
  const pausedByUser = useRef(false);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reducedMotion) pausedByUser.current = true;

    const applyRate = () => {
      video.playbackRate = DEMO_PLAYBACK_RATE;
    };
    applyRate();
    video.addEventListener("loadedmetadata", applyRate);
    // Some browsers reset the rate when the source restarts.
    video.addEventListener("play", applyRate);

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !pausedByUser.current) {
          video.play().catch(() => {});
        } else if (!entry.isIntersecting) {
          video.pause();
        }
      },
      { threshold: 0.35 },
    );
    observer.observe(video);

    return () => {
      observer.disconnect();
      video.removeEventListener("loadedmetadata", applyRate);
      video.removeEventListener("play", applyRate);
    };
  }, []);

  const toggle = () => {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) {
      pausedByUser.current = false;
      video.play().catch(() => {});
    } else {
      pausedByUser.current = true;
      video.pause();
    }
  };

  return (
    <RailSection id="demo" aria-labelledby="demo-heading">
      <div className="px-5 pt-24 pb-12 text-center sm:px-12 sm:pt-28">
        <SectionHeading id="demo-heading" className="mx-auto max-w-[30rem]">
          See it work, start to finish.
        </SectionHeading>
        <p className="mx-auto mt-5 max-w-[34rem] text-sm leading-relaxed text-muted-foreground">
          A real session on the live app: a cited answer from a PDF, a web search, the
          weather, a bug report approved by an admin, and the same chat on a phone.
        </p>
      </div>

      <div className="px-5 pb-24 sm:px-12 sm:pb-28">
        <div className="relative mx-auto max-w-5xl overflow-hidden rounded-xl border border-line bg-card">
          <video
            ref={videoRef}
            src={SRC}
            poster={POSTER}
            muted
            loop
            playsInline
            preload="metadata"
            aria-label="Demo of Chat: document answers with citations, web search, weather, bug reports and the admin dashboard"
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            className="block aspect-video w-full"
          />
          <button
            type="button"
            onClick={toggle}
            aria-label={playing ? "Pause the demo" : "Play the demo"}
            className="absolute right-3 bottom-3 flex size-9 items-center justify-center rounded-[4px] border border-line bg-background/80 text-foreground backdrop-blur-sm transition-colors hover:bg-background"
          >
            {playing ? <Pause aria-hidden className="size-4" /> : <Play aria-hidden className="size-4" />}
          </button>
        </div>
      </div>
    </RailSection>
  );
}
