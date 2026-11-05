"use client";

import React, { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
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

export default function AuthForm({ mode }: AuthFormProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const isLogin = mode === "login";
  const titleText = isLogin
    ? "Sign In to Your Account"
    : "Create a New Account";
  const buttonText = isLogin ? "Login" : "Register";
  const registered = searchParams.get("registered") === "success";

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);

    const trimmedEmail = email.trim();
    const trimmedPassword = password.trim();

    if (!trimmedEmail || !trimmedPassword) {
      setError("Both email and password are required.");
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
          : "An unexpected error occurred. Please try again.";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="w-full max-w-md rounded-2xl border border-border bg-card p-8 shadow-sm">
      <h2 className="mb-2 text-center text-2xl font-bold text-foreground">
        {titleText}
      </h2>
      {registered && isLogin && (
        <p
          className="mb-4 text-center text-sm text-green-600 dark:text-green-400"
          role="status"
        >
          Account created. You can sign in now.
        </p>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label
            htmlFor="email"
            className="mb-1 block text-sm font-medium text-foreground"
          >
            Email Address
          </label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-lg border border-input bg-background px-4 py-2.5 text-foreground outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring"
            placeholder="you@example.com"
            required
            disabled={isLoading}
            autoComplete="email"
          />
        </div>

        <div>
          <label
            htmlFor="password"
            className="mb-1 block text-sm font-medium text-foreground"
          >
            Password
          </label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-lg border border-input bg-background px-4 py-2.5 text-foreground outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring"
            placeholder="••••••••"
            required
            disabled={isLoading}
            minLength={8}
            autoComplete={isLogin ? "current-password" : "new-password"}
          />
        </div>

        {error && (
          <p className="text-sm font-medium text-destructive" role="alert">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={isLoading}
          className="w-full rounded-lg bg-primary py-2.5 font-medium text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isLoading ? "Processing…" : buttonText}
        </button>
      </form>

      <div className="mt-6 text-center text-sm text-muted-foreground">
        {isLogin ? (
          <p>
            Don&apos;t have an account?{" "}
            <Link
              href="/register"
              className="font-semibold text-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Sign Up
            </Link>
          </p>
        ) : (
          <p>
            Already have an account?{" "}
            <Link
              href="/login"
              className="font-semibold text-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Sign In
            </Link>
          </p>
        )}
      </div>
    </div>
  );
}
