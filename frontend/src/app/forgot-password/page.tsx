"use client";

import React, { useState } from "react";
import Link from "next/link";
import { ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { AUTH_MODE, getSupabaseClient } from "@/lib/supabase";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setStatusMsg(null);
    if (AUTH_MODE !== "supabase") {
      setStatusMsg("Password recovery applies when Supabase Auth is enabled (NEXT_PUBLIC_AUTH_MODE=supabase).");
      return;
    }
    const supabase = getSupabaseClient();
    if (!supabase) {
      setErrorMsg("Supabase client is not configured.");
      return;
    }
    setSubmitting(true);
    try {
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/login`,
      });
      if (error) throw new Error(error.message);
      setStatusMsg("If an account exists for that email, a recovery link has been sent.");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to send recovery email");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <Card className="w-full max-w-md border-border bg-surface p-6">
        <div className="mb-5 flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-accent/20 text-accent">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-foreground">Reset password</h1>
            <p className="text-xs text-muted">Recover access to your FlowSentry workspace</p>
          </div>
        </div>

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label htmlFor="reset-email" className="mb-1.5 block text-xs font-medium text-muted">
              Account email
            </label>
            <Input
              id="reset-email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="engineer@company.com"
            />
          </div>

          {errorMsg ? (
            <div className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
              {errorMsg}
            </div>
          ) : null}
          {statusMsg ? (
            <div className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">
              {statusMsg}
            </div>
          ) : null}

          <Button type="submit" className="w-full" disabled={submitting}>
            {submitting ? "Sending..." : "Send recovery email"}
          </Button>
        </form>

        <div className="mt-5 border-t border-border pt-4 text-center text-xs text-muted">
          <Link href="/login" className="text-accent hover:underline">
            Back to sign in
          </Link>
        </div>
      </Card>
    </div>
  );
}
