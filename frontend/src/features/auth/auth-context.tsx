"use client";

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { getStoredToken, setStoredToken } from "@/lib/api-client";
import { AUTH_MODE, getSupabaseClient } from "@/lib/supabase";
import { apiService } from "@/services/api";
import type { ProjectEnvironment, User, Workspace } from "@/types/api";

interface AuthContextValue {
  user: User | null;
  workspaces: Workspace[];
  activeWorkspace: Workspace | null;
  activeEnvironment: ProjectEnvironment | "all";
  isLoading: boolean;
  error: string | null;
  setActiveWorkspaceId: (id: string) => void;
  setActiveEnvironment: (env: ProjectEnvironment | "all") => void;
  refreshAuth: () => Promise<void>;
  signInWithDevToken: (email: string, name?: string) => Promise<void>;
  signInWithSupabase: (email: string, password: string) => Promise<void>;
  signUpWithSupabase: (email: string, password: string, name?: string) => Promise<string | null>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const WORKSPACE_STORAGE_KEY = "flowsentry_active_workspace";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [activeWorkspaceId, setActiveWorkspaceIdState] = useState<string | null>(null);
  const [activeEnvironment, setActiveEnvironment] = useState<ProjectEnvironment | "all">("all");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const setActiveWorkspaceId = useCallback((id: string) => {
    setActiveWorkspaceIdState(id);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(WORKSPACE_STORAGE_KEY, id);
    }
  }, []);

  const refreshAuth = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      let token = getStoredToken();
      if (!token && AUTH_MODE === "supabase") {
        const supabase = getSupabaseClient();
        if (supabase) {
          const { data } = await supabase.auth.getSession();
          token = data.session?.access_token ?? null;
          if (token) setStoredToken(token);
        }
      }
      if (!token) {
        setUser(null);
        setWorkspaces([]);
        setIsLoading(false);
        return;
      }

      const me = await apiService.getMe();
      setUser(me.user);
      setWorkspaces(me.workspaces);

      const savedId =
        typeof window !== "undefined" ? window.localStorage.getItem(WORKSPACE_STORAGE_KEY) : null;
      const validSaved = me.workspaces.find((w) => w.id === savedId);
      if (validSaved) {
        setActiveWorkspaceIdState(validSaved.id);
      } else if (me.workspaces.length > 0) {
        setActiveWorkspaceIdState(me.workspaces[0].id);
      } else {
        setActiveWorkspaceIdState(null);
      }
    } catch (err) {
      setUser(null);
      setWorkspaces([]);
      setStoredToken(null);
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshAuth();
  }, [refreshAuth]);

  const signInWithDevToken = useCallback(
    async (email: string, name?: string) => {
      const resp = await apiService.issueDevToken(email, name);
      setStoredToken(resp.access_token);
      await refreshAuth();
    },
    [refreshAuth]
  );

  const signInWithSupabase = useCallback(
    async (email: string, password: string) => {
      const supabase = getSupabaseClient();
      if (!supabase) {
        throw new Error("Supabase client is not configured");
      }
      const { data, error: authError } = await supabase.auth.signInWithPassword({ email, password });
      if (authError || !data.session) {
        throw new Error(authError?.message || "Sign-in failed");
      }
      setStoredToken(data.session.access_token);
      await refreshAuth();
    },
    [refreshAuth]
  );

  const signUpWithSupabase = useCallback(
    async (email: string, password: string, name?: string): Promise<string | null> => {
      const supabase = getSupabaseClient();
      if (!supabase) {
        throw new Error("Supabase client is not configured");
      }
      const { data, error: signUpError } = await supabase.auth.signUp({
        email,
        password,
        options: { data: { name } },
      });
      if (signUpError) {
        throw new Error(signUpError.message);
      }
      if (data.session?.access_token) {
        setStoredToken(data.session.access_token);
        await refreshAuth();
        return null;
      }
      return "Check your email to verify your account before signing in.";
    },
    [refreshAuth]
  );

  const signOut = useCallback(async () => {
    const supabase = getSupabaseClient();
    if (supabase) {
      await supabase.auth.signOut().catch(() => undefined);
    }
    setStoredToken(null);
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(WORKSPACE_STORAGE_KEY);
    }
    setUser(null);
    setWorkspaces([]);
    setActiveWorkspaceIdState(null);
  }, []);

  const activeWorkspace = useMemo(
    () => workspaces.find((w) => w.id === activeWorkspaceId) || workspaces[0] || null,
    [workspaces, activeWorkspaceId]
  );

  return (
    <AuthContext.Provider
      value={{
        user,
        workspaces,
        activeWorkspace,
        activeEnvironment,
        isLoading,
        error,
        setActiveWorkspaceId,
        setActiveEnvironment,
        refreshAuth,
        signInWithDevToken,
        signInWithSupabase,
        signUpWithSupabase,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
