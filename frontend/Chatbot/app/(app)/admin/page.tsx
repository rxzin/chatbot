"use client";

import { Suspense } from "react";
import { AdminDashboard } from "@/components/admin/AdminDashboard";

export default function AdminPage() {
  return (
    <Suspense fallback={null}>
      <AdminDashboard />
    </Suspense>
  );
}
