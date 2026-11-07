"use client";

import { ChatShell } from "@/components/chat/ChatShell";
import { useAuth } from "@/hooks/useAuth";
import type { Metadata } from "next";
export const metadata: Metadata = {
  title: "Chat Session",
  robots: {
    index: false,
    follow: false,
  },
};
export default function ChatPage() {
  const { isAuthenticated } = useAuth({
    redirectTo: "/login?redirect=/chat",
  });

  if (isAuthenticated === null) {
    return (
      <main className="flex min-h-dvh items-center justify-center bg-background text-sm text-muted-foreground">
        Checking session…
      </main>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return <ChatShell />;
}
