"use client";

import { createContext, useContext } from "react";
import type { Look } from "@/hooks/usePointerLook";
import { lookExpression, type AvatarAnimation } from "./definition";

export type AuthField = "email" | "password";
export type Reaction = "error" | "success" | null;

export type MoodState = {
  /** The field that has focus, and where it sits relative to the avatar. */
  focus: { field: AuthField; look: Look } | null;
  reaction: Reaction;
};

export type MoodAction =
  | { type: "focus"; field: AuthField; look: Look }
  | { type: "blur"; field: AuthField; valid: boolean }
  | { type: "submitted"; ok: boolean }
  | { type: "settled" };

export const initialMood: MoodState = { focus: null, reaction: null };

export function moodReducer(state: MoodState, action: MoodAction): MoodState {
  switch (action.type) {
    case "focus":
      return { ...state, focus: { field: action.field, look: action.look } };
    case "blur":
      return {
        focus: state.focus?.field === action.field ? null : state.focus,
        reaction: action.valid ? state.reaction : "error",
      };
    case "submitted":
      return { ...state, reaction: action.ok ? "success" : "error" };
    case "settled":
      return state.reaction ? { ...state, reaction: null } : state;
  }
}

/** The avatar plays one animation or holds one expression, never both. */
export type AvatarTarget =
  | { animation: AvatarAnimation; expression?: undefined }
  | { expression: string; animation?: undefined };

/**
 * What the avatar should do for a mood, most pressing first: a reaction plays out, then a
 * password hides its eyes, then a focused field is watched, then the cursor is followed,
 * then idle.
 */
export function avatarTargetFor(mood: MoodState, pointer: Look | null): AvatarTarget {
  if (mood.reaction) return { animation: mood.reaction };
  if (mood.focus?.field === "password") return { expression: "hiding" };
  if (mood.focus) return { expression: lookExpression(mood.focus.look, "watch") };
  return pointer ? { expression: lookExpression(pointer, "look") } : { animation: "idle" };
}

/** What a form tells the avatar. Outside an AuthShell every call does nothing. */
export type AuthReactions = {
  fieldFocused: (field: AuthField, element: Element) => void;
  fieldBlurred: (field: AuthField, valid: boolean) => void;
  submitted: (ok: boolean) => void;
};

const noop = () => undefined;

export const AuthReactionsContext = createContext<AuthReactions>({
  fieldFocused: noop,
  fieldBlurred: noop,
  submitted: noop,
});

export const useAuthReactions = () => useContext(AuthReactionsContext);
