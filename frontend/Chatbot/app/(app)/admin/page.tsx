"use client";

import { Suspense } from "react";
import { AdminDashboard } from "@/components/admin/AdminDashboard";
import type { Metadata } from "next";
export const metadata: Metadata = {
  title: "Chat Session",
  robots: {
    index: false,
    follow: false,
  },
};
export default function AdminPage() {
  return (
    <Suspense fallback={null}>
      <AdminDashboard />
    </Suspense>
  );
}
