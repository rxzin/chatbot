"use client";

import { LogOut, MessageSquare } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/hooks/useAuth";
import { ADMIN_PERMISSION } from "@/lib/api/authApi";
import { useLogout } from "@/hooks/useLogout";
import { AuditLogTab } from "./AuditLogTab";
import { LoadingPanel } from "./StatePanels";
import { SummaryCards } from "./SummaryCards";
import { TicketsTab } from "./TicketsTab";
import { UsersTab } from "./UsersTab";

const TABS = [
  {
    value: "bugs",
    label: "Bug reports",
    permission: "ticket:manage",
    content: <TicketsTab />,
  },
  {
    value: "audit",
    label: "Audit log",
    permission: "audit:read",
    content: <AuditLogTab />,
  },
  {
    value: "users",
    label: "Users & sessions",
    permission: "users:ban",
    content: <UsersTab />,
  },
];

export function AdminDashboard() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { isAuthenticated, user } = useAuth({
    redirectTo: "/login?redirect=/admin",
    requiredPermission: ADMIN_PERMISSION,
    permissionDeniedRedirect: "/chat",
  });
  const { isLoggingOut, handleLogout } = useLogout();

  if (isAuthenticated === null) {
    return (
      <div className="container mx-auto max-w-6xl px-4 py-10">
        <LoadingPanel />
      </div>
    );
  }

  if (!isAuthenticated || !user) return null;

  const tabs = TABS.filter((tab) => user.permissions.includes(tab.permission));
  const requested = searchParams.get("tab");
  const activeTab = tabs.some((tab) => tab.value === requested)
    ? (requested as string)
    : tabs[0]?.value;

  return (
    <div className="container mx-auto max-w-6xl space-y-6 px-4 py-10">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Admin dashboard</h1>
          <p className="mt-2 text-muted-foreground">
            Review bug reports, monitor requests, and manage user access.
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <Button asChild variant="outline" size="sm">
            <Link href="/chat">
              <MessageSquare />
              Chat
            </Link>
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleLogout}
            disabled={isLoggingOut}
          >
            <LogOut />
            Log out
          </Button>
        </div>
      </div>

      {user.permissions.includes("audit:read") && <SummaryCards />}

      <Tabs
        value={activeTab}
        // Updates the URL without a route change, so switching tabs never reloads the page.
        onValueChange={(tab) =>
          window.history.replaceState(null, "", `${pathname}?tab=${tab}`)
        }
      >
        <TabsList>
          {tabs.map((tab) => (
            <TabsTrigger key={tab.value} value={tab.value}>
              {tab.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {tabs.map((tab) => (
          <TabsContent key={tab.value} value={tab.value} className="mt-4">
            {tab.content}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
