"use client";

import React, { useId, useState } from "react";
import { Loader2 } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  ADMIN_PERMISSION,
  fetchCurrentUser,
  login,
  register,
} from "@/lib/api/authApi";
import { useAuthReactions, type AuthField } from "./avatar/reactions";

type AuthFormProps = {
  mode: "login" | "register";
};

/** Admins land on the dashboard. If the role check fails, login still succeeds. */
async function defaultPathAfterLogin(): Promise<string> {
  try {
    const user = await fetchCurrentUser();
    return user.permissions.includes(ADMIN_PERMISSION) ? "/admin" : "/chat";
  } catch {
    return "/chat";
  }
}

/** Long enough for the avatar's success reaction to be seen before the page changes. */
const SUCCESS_PAUSE_MS = 900;

/** What is wrong with a filled-in field, or "" when nothing is. */
function problemWith(field: AuthField, value: string): string {
  if (field === "email") {
    return /^\S+@\S+\.\S+$/.test(value.trim()) ? "" : "That doesn't look like an email address.";
  }
  return value.length >= 8 ? "" : "Use at least 8 characters.";
}

const inputClass =
  "h-11 rounded-[4px] border-line bg-background px-3 text-foreground dark:bg-background";

export default function AuthForm({ mode }: AuthFormProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const reactions = useAuthReactions();
  const errorId = useId();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [problems, setProblems] = useState({ email: "", password: "" });
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const isLogin = mode === "login";
  const registered = searchParams.get("registered") === "success";

  /** An empty field is left alone on blur: tabbing through isn't a mistake yet. */
  const checkOnBlur = (field: AuthField, value: string) => {
    const problem = value.trim() ? problemWith(field, value) : "";
    setProblems((before) => ({ ...before, [field]: problem }));
    reactions.fieldBlurred(field, !problem);
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError("");

    const trimmedEmail = email.trim();
    const trimmedPassword = password.trim();

    if (!trimmedEmail || !trimmedPassword) {
      setError("Enter your email and password.");
      reactions.submitted(false);
      return;
    }

    const found = {
      email: problemWith("email", trimmedEmail),
      password: problemWith("password", trimmedPassword),
    };
    setProblems(found);
    if (found.email || found.password) {
      reactions.submitted(false);
      return;
    }

    setIsLoading(true);
    try {
      let destination: string;
      if (isLogin) {
        await login(trimmedEmail, trimmedPassword);
        const redirect = searchParams.get("redirect");
        // "//evil.com" also starts with "/", but browsers treat it as another site.
        const isLocalPath =
          redirect?.startsWith("/") && !/^\/[/\\]/.test(redirect);
        destination = isLocalPath && redirect ? redirect : await defaultPathAfterLogin();
      } else {
        await register(trimmedEmail, trimmedPassword);
        destination = "/login?registered=success";
      }
      reactions.submitted(true);
      await new Promise((resolve) => setTimeout(resolve, SUCCESS_PAUSE_MS));
      router.push(destination);
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : "Something went wrong. Please try again.";
      setError(message);
      reactions.submitted(false);
      // Only a failure hands the form back. After a success it stays busy until the
      // next page replaces it, so it can't be submitted twice.
      setIsLoading(false);
    }
  };

  const describedBy = (field: AuthField, hint?: string) =>
    problems[field] ? `${errorId}-${field}` : error ? errorId : hint;

  return (
    <div className="w-full max-w-[24rem]">
      <h1 className="font-display text-[2.2rem] leading-tight font-medium tracking-[-0.02em]">
        {isLogin ? "Welcome back" : "Create your account"}
      </h1>
      <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
        {isLogin
          ? "Sign in to pick up your conversations where you left them."
          : "All you need is an email address and a password."}
      </p>

      {registered && isLogin && (
        <p
          role="status"
          className="mt-6 rounded-[4px] border border-live/40 px-3 py-2.5 text-sm text-live"
        >
          Account created. Sign in to continue.
        </p>
      )}

      <form onSubmit={handleSubmit} noValidate className="mt-10">
        <FieldGroup>
          <Field data-invalid={problems.email || error ? true : undefined}>
            <FieldLabel htmlFor="email">Email</FieldLabel>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onFocus={(e) => reactions.fieldFocused("email", e.currentTarget)}
              onBlur={() => checkOnBlur("email", email)}
              placeholder="you@example.com"
              required
              disabled={isLoading}
              autoComplete="email"
              aria-invalid={problems.email || error ? true : undefined}
              aria-describedby={describedBy("email")}
              className={inputClass}
            />
            {problems.email && (
              <FieldError id={`${errorId}-email`}>{problems.email}</FieldError>
            )}
          </Field>

          <Field data-invalid={problems.password || error ? true : undefined}>
            <FieldLabel htmlFor="password">Password</FieldLabel>
            <div className="relative">
              <Input
                id="password"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onFocus={(e) => reactions.fieldFocused("password", e.currentTarget)}
                onBlur={() => checkOnBlur("password", password)}
                required
                disabled={isLoading}
                minLength={8}
                autoComplete={isLogin ? "current-password" : "new-password"}
                aria-invalid={problems.password || error ? true : undefined}
                aria-describedby={describedBy("password", !isLogin ? "password-hint" : undefined)}
                className={`${inputClass} pr-16`}
              />
              <button
                type="button"
                onClick={() => setShowPassword((shown) => !shown)}
                aria-controls="password"
                aria-pressed={showPassword}
                aria-label="Show password"
                className="absolute inset-y-0 right-0 flex items-center px-3 text-xs text-muted-foreground transition-colors hover:text-foreground"
              >
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
            {problems.password ? (
              <FieldError id={`${errorId}-password`}>{problems.password}</FieldError>
            ) : (
              !isLogin && (
                <FieldDescription id="password-hint">At least 8 characters.</FieldDescription>
              )
            )}
          </Field>

          {error && <FieldError id={errorId}>{error}</FieldError>}

          <Button
            type="submit"
            disabled={isLoading}
            className="h-11 w-full rounded-[4px] font-medium"
          >
            {isLoading && <Loader2 aria-hidden className="animate-spin" />}
            {isLoading
              ? isLogin
                ? "Signing in…"
                : "Creating account…"
              : isLogin
                ? "Sign in"
                : "Create account"}
          </Button>
        </FieldGroup>
      </form>

      <p className="mt-7 text-sm text-muted-foreground">
        {isLogin ? "No account yet? " : "Already have an account? "}
        <Link
          href={isLogin ? "/register" : "/login"}
          prefetch={false}
          className="text-foreground underline-offset-4 hover:underline"
        >
          {isLogin ? "Create one" : "Sign in"}
        </Link>
      </p>
    </div>
  );
}
