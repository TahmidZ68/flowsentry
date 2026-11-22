"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  AlertOctagon,
  Bell,
  FlaskConical,
  FolderKanban,
  GitBranch,
  LayoutDashboard,
  LogOut,
  Menu,
  Plug,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Target,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { LoadingState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";
import { cn } from "@/lib/utils";
import { apiService } from "@/services/api";
import type { ProjectEnvironment } from "@/types/api";

export const NAV_ITEMS = [
  { href: "/overview", label: "Overview", icon: LayoutDashboard },
  { href: "/incidents", label: "Incidents", icon: AlertOctagon },
  { href: "/workflows", label: "Workflows", icon: GitBranch },
  { href: "/monitors", label: "Outcome Monitors", icon: Target },
  { href: "/investigations", label: "Investigations", icon: Sparkles },
  { href: "/integrations", label: "Integrations", icon: Plug },
  { href: "/projects", label: "Projects", icon: FolderKanban },
  { href: "/notifications", label: "Notifications", icon: Bell },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const {
    user,
    workspaces,
    activeWorkspace,
    activeEnvironment,
    isLoading,
    setActiveWorkspaceId,
    setActiveEnvironment,
    refreshAuth,
    signOut,
  } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [seedingDemo, setSeedingDemo] = useState(false);

  const handleSeedDemo = async () => {
    setSeedingDemo(true);
    try {
      const demoWs = await apiService.seedDemoWorkspace();
      await refreshAuth();
      setActiveWorkspaceId(demoWs.id);
    } finally {
      setSeedingDemo(false);
    }
  };

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace("/login");
    }
  }, [isLoading, user, router]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-6">
        <div className="w-full max-w-sm">
          <LoadingState label="Verifying FlowSentry session..." />
        </div>
      </div>
    );
  }

  if (!user) {
    return null;
  }

  const sidebarContent = (
    <div className="flex h-full flex-col justify-between">
      <div>
        <div className="flex h-14 items-center gap-2.5 border-b border-border px-4">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-accent/20 text-accent">
            <ShieldCheck className="h-4 w-4" />
          </div>
          <div>
            <span className="text-sm font-semibold tracking-tight text-foreground">FlowSentry</span>
            <span className="ml-2 rounded bg-surface-elevated px-1.5 py-0.5 font-mono text-[10px] text-muted">
              v0.1
            </span>
          </div>
        </div>

        <nav className="space-y-0.5 p-3" aria-label="Main navigation">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMobileOpen(false)}
                className={cn(
                  "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                  active
                    ? "bg-accent/15 font-medium text-indigo-300"
                    : "text-muted hover:bg-surface-elevated hover:text-foreground"
                )}
              >
                <Icon className={cn("h-4 w-4", active ? "text-accent" : "text-slate-500")} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>

      <div className="space-y-2 border-t border-border p-3">
        <div className="rounded-md border border-border bg-background/60 p-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-foreground">
              {activeWorkspace ? activeWorkspace.name : "No Workspace"}
            </span>
            {activeWorkspace ? (
              <Badge variant={activeWorkspace.is_demo ? "warning" : "accent"}>
                {activeWorkspace.is_demo ? "DEMO" : activeWorkspace.plan.toUpperCase()}
              </Badge>
            ) : null}
          </div>
          <p className="mt-1 truncate text-[11px] text-muted">{user.email}</p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          className="w-full text-xs"
          onClick={() => void handleSeedDemo()}
          disabled={seedingDemo}
        >
          <FlaskConical className="h-3.5 w-3.5 text-amber-400" />
          {seedingDemo ? "Preparing Demo..." : "Seed / Reset Demo"}
        </Button>
      </div>
    </div>
  );

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      {/* Desktop Sidebar */}
      <aside className="hidden w-60 shrink-0 border-r border-border bg-surface lg:block">
        {sidebarContent}
      </aside>

      {/* Mobile Drawer */}
      {mobileOpen ? (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <div className="w-64 border-r border-border bg-surface">{sidebarContent}</div>
          <button
            type="button"
            aria-label="Close navigation"
            className="flex-1 bg-black/60"
            onClick={() => setMobileOpen(false)}
          />
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Topbar */}
        <header className="flex h-14 items-center justify-between gap-3 border-b border-border bg-surface/80 px-4 backdrop-blur-sm">
          <div className="flex items-center gap-2.5">
            <Button
              variant="ghost"
              size="sm"
              className="lg:hidden"
              onClick={() => setMobileOpen(!mobileOpen)}
              aria-label="Toggle menu"
            >
              {mobileOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
            </Button>

            <div className="flex items-center gap-2">
              <Select
                aria-label="Select workspace"
                className="h-8 w-44 text-xs"
                value={activeWorkspace?.id || ""}
                onChange={(e) => setActiveWorkspaceId(e.target.value)}
                disabled={workspaces.length === 0}
              >
                {workspaces.length === 0 ? (
                  <option value="">Create a workspace</option>
                ) : (
                  workspaces.map((ws) => (
                    <option key={ws.id} value={ws.id}>
                      {ws.name} ({ws.role})
                    </option>
                  ))
                )}
              </Select>

              <Select
                aria-label="Select environment"
                className="hidden h-8 w-36 text-xs sm:block"
                value={activeEnvironment}
                onChange={(e) => setActiveEnvironment(e.target.value as ProjectEnvironment | "all")}
              >
                <option value="all">All environments</option>
                <option value="production">Production</option>
                <option value="staging">Staging</option>
                <option value="development">Development</option>
              </Select>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <div className="relative hidden md:block">
              <Search className="pointer-events-none absolute left-2.5 top-2 h-4 w-4 text-slate-500" />
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search workflows, incidents..."
                className="h-8 w-56 pl-8 text-xs"
                aria-label="Global search"
              />
            </div>

            <Link
              href="/notifications"
              className="flex h-8 w-8 items-center justify-center rounded-md border border-border bg-background text-muted hover:text-foreground"
              aria-label="Notification center"
            >
              <Activity className="h-4 w-4" />
            </Link>

            <Button
              variant="ghost"
              size="sm"
              onClick={() => void signOut()}
              title="Sign out"
              aria-label="Sign out"
            >
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </header>

        <main className="flex-1 p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
