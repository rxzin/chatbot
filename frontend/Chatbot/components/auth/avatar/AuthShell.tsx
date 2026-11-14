"use client";

import dynamic from "next/dynamic";
import Image from "next/image";
import { useEffect, useMemo, useReducer, useRef, type ReactNode } from "react";
import { AnimatedThemeToggler } from "@/components/ui/animated-theme-toggler";
import { lookToward, usePointerLook } from "@/hooks/usePointerLook";
import { AvatarGlow } from "./AvatarGlow";
import { LOOK_STEPS } from "./definition";
import {
  AuthReactionsContext,
  avatarTargetFor,
  initialMood,
  moodReducer,
  type AuthReactions,
} from "./reactions";

const AuthAvatar = dynamic(() => import("./AuthAvatar"), { ssr: false });

/** A gaze is capped to a circle of this radius; 1 is the avatar's furthest look. */
const LOOK_LIMIT = 1;
/** With the cursor still for this long, the avatar goes back to idling. */
const REST_AFTER_MS = 2600;
/** A reaction clears itself when its animation ends; this catches the case where it can't report. */
const REACTION_TIMEOUT_MS = 3000;

/**
 * The two-panel auth page: the avatar on the left, the form passed as children on the
 * right. It owns the avatar's mood and hands the form the calls that change it.
 */
export function AuthShell({ children }: { children: ReactNode }) {
  const [mood, dispatch] = useReducer(moodReducer, initialMood);
  const stage = useRef<HTMLDivElement>(null);
  const pointer = usePointerLook(stage, mood.focus === null, {
    limit: LOOK_LIMIT,
    steps: LOOK_STEPS,
    restAfterMs: REST_AFTER_MS,
  });

  const reactions = useMemo<AuthReactions>(
    () => ({
      fieldFocused: (field, element) => {
        if (!stage.current) return;
        dispatch({ type: "focus", field, look: lookToward(stage.current, element, LOOK_LIMIT) });
      },
      fieldBlurred: (field, valid) => dispatch({ type: "blur", field, valid }),
      submitted: (ok) => dispatch({ type: "submitted", ok }),
    }),
    [],
  );

  useEffect(() => {
    if (!mood.reaction) return;
    const timer = window.setTimeout(() => dispatch({ type: "settled" }), REACTION_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, [mood.reaction]);

  const target = avatarTargetFor(mood, pointer);

  return (
    <AuthReactionsContext.Provider value={reactions}>
      <div className="landing grid min-h-svh grid-rows-[auto_1fr] lg:grid-cols-2 lg:grid-rows-1">
        <aside className="relative m-3 flex min-h-[19rem] items-center justify-center overflow-hidden rounded-2xl lg:mr-0 lg:min-h-0">
          <Image
            src="/light_background.jpg"
            alt=""
            fill
            sizes="(min-width: 1024px) 50vw, 100vw"
            className="object-cover dark:hidden"
          />
          <Image
            src="/dark_background.jpeg"
            alt=""
            fill
            sizes="(min-width: 1024px) 50vw, 100vw"
            className="hidden object-cover dark:block"
          />
          <div ref={stage} className="relative aspect-square w-[min(52vw,13rem)] lg:w-[clamp(17rem,27vw,24rem)]">
            <AvatarGlow reaction={mood.reaction} />
            <div className="relative size-full">
              <AuthAvatar target={target} onAnimationEnd={() => dispatch({ type: "settled" })} />
            </div>
          </div>
        </aside>

        <div className="flex flex-col">
          <header className="flex h-[72px] items-center justify-end px-6 md:px-10">
            <AnimatedThemeToggler className="flex size-9 items-center justify-center rounded-[4px] text-muted-foreground transition-colors hover:text-foreground [&_svg]:size-[18px]" />
          </header>
          <main className="flex flex-1 items-center justify-center px-6 pt-6 pb-20 md:px-10">
            {children}
          </main>
        </div>
      </div>
    </AuthReactionsContext.Provider>
  );
}
