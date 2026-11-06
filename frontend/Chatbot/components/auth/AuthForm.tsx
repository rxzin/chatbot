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

const inputClass =
  "h-10 rounded-[4px] border-line bg-background px-3 text-foreground dark:bg-background";

export default function AuthForm({ mode }: AuthFormProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const errorId = useId();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const isLogin = mode === "login";
  const registered = searchParams.get("registered") === "success";

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);

    const trimmedEmail = email.trim();
    const trimmedPassword = password.trim();

    if (!trimmedEmail || !trimmedPassword) {
      setError("Enter your email and password.");
      setIsLoading(false);
      return;
    }

    try {
      if (isLogin) {
        await login(trimmedEmail, trimmedPassword);
        const redirect = searchParams.get("redirect");
        // "//evil.com" also starts with "/", but browsers treat it as another site.
        const isLocalPath =
          redirect?.startsWith("/") && !/^\/[/\\]/.test(redirect);
        router.push(
          isLocalPath && redirect ? redirect : await defaultPathAfterLogin()
        );
      } else {
        await register(trimmedEmail, trimmedPassword);
        router.push("/login?registered=success");
      }
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : "Something went wrong. Please try again.";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="w-full max-w-[24rem] rounded-xl border border-line bg-background p-7 sm:p-9">
      <h1 className="font-display text-[1.9rem] leading-tight font-medium tracking-[-0.02em]">
        {isLogin ? "Welcome back" : "Create your account"}
      </h1>
      <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
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

      <form onSubmit={handleSubmit} className="mt-8">
        <FieldGroup>
          <Field data-invalid={error ? true : undefined}>
            <FieldLabel htmlFor="email">Email</FieldLabel>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              disabled={isLoading}
              autoComplete="email"
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? errorId : undefined}
              className={inputClass}
            />
          </Field>

          <Field data-invalid={error ? true : undefined}>
            <FieldLabel htmlFor="password">Password</FieldLabel>
            <div className="relative">
              <Input
                id="password"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={isLoading}
                minLength={8}
                autoComplete={isLogin ? "current-password" : "new-password"}
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? errorId : !isLogin ? "password-hint" : undefined}
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
            {!isLogin && (
              <FieldDescription id="password-hint">At least 8 characters.</FieldDescription>
            )}
          </Field>

          {error && <FieldError id={errorId}>{error}</FieldError>}

          <Button
            type="submit"
            disabled={isLoading}
            className="h-10 w-full rounded-[4px] font-medium"
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
