"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ShieldCheck } from "lucide-react";
import { z } from "zod";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/features/auth/auth-context";
import { AUTH_MODE } from "@/lib/supabase";

const loginSchema = z.object({
  email: z.string().email("Enter a valid email address"),
  password: z.string().optional(),
  name: z.string().optional(),
});

type LoginFormValues = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const router = useRouter();
  const { signInWithDevToken, signInWithSupabase } = useAuth();
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
  });

  const onSubmit = async (values: LoginFormValues) => {
    setServerError(null);
    try {
      if (AUTH_MODE === "supabase") {
        if (!values.password || values.password.length < 6) {
          setServerError("Password must be at least 6 characters");
          return;
        }
        await signInWithSupabase(values.email, values.password);
      } else {
        await signInWithDevToken(values.email, values.name);
      }
      router.replace("/overview");
    } catch (err) {
      setServerError(err instanceof Error ? err.message : "Authentication failed");
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <Card className="w-full max-w-md border-border bg-surface p-6">
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-accent/20 text-accent">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-base font-semibold text-foreground">Sign in to FlowSentry</h1>
              <p className="text-xs text-muted">Your workflows run. Make sure they work.</p>
            </div>
          </div>
          <Badge variant={AUTH_MODE === "supabase" ? "healthy" : "warning"}>
            {AUTH_MODE === "supabase" ? "Supabase Auth" : "Local Dev Mode"}
          </Badge>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <div>
            <label htmlFor="email" className="mb-1.5 block text-xs font-medium text-muted">
              Work email
            </label>
            <Input
              id="email"
              type="email"
              placeholder="engineer@company.com"
              {...register("email")}
            />
            {errors.email ? (
              <p className="mt-1 text-xs text-red-400">{errors.email.message}</p>
            ) : null}
          </div>

          {AUTH_MODE === "supabase" ? (
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <label htmlFor="password" className="text-xs font-medium text-muted">
                  Password
                </label>
                <Link href="/forgot-password" className="text-xs text-accent hover:underline">
                  Forgot password?
                </Link>
              </div>
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                {...register("password")}
              />
            </div>
          ) : (
            <div>
              <label htmlFor="name" className="mb-1.5 block text-xs font-medium text-muted">
                Display name (optional, local dev only)
              </label>
              <Input id="name" type="text" placeholder="Alex Rivera" {...register("name")} />
            </div>
          )}

          {serverError ? (
            <div className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
              {serverError}
            </div>
          ) : null}

          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? "Signing in..." : "Sign in"}
          </Button>
        </form>

        <div className="mt-5 border-t border-border pt-4 text-center text-xs text-muted">
          Don&apos;t have an account?{" "}
          <Link href="/register" className="text-accent hover:underline">
            Create account
          </Link>
        </div>
      </Card>
    </div>
  );
}
