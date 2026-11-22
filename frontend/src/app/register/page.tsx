"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ShieldCheck } from "lucide-react";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/features/auth/auth-context";
import { AUTH_MODE } from "@/lib/supabase";

const registerSchema = z.object({
  name: z.string().min(2, "Enter your name"),
  email: z.string().email("Enter a valid email address"),
  password: z.string().optional(),
});

type RegisterValues = z.infer<typeof registerSchema>;

export default function RegisterPage() {
  const router = useRouter();
  const { signUpWithSupabase, signInWithDevToken } = useAuth();
  const [serverError, setServerError] = useState<string | null>(null);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
  });

  const onSubmit = async (values: RegisterValues) => {
    setServerError(null);
    setInfoMessage(null);
    try {
      if (AUTH_MODE === "supabase") {
        if (!values.password || values.password.length < 8) {
          setServerError("Password must be at least 8 characters");
          return;
        }
        const message = await signUpWithSupabase(values.email, values.password, values.name);
        if (message) {
          setInfoMessage(message);
          return;
        }
      } else {
        await signInWithDevToken(values.email, values.name);
      }
      router.replace("/overview");
    } catch (err) {
      setServerError(err instanceof Error ? err.message : "Registration failed");
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <Card className="w-full max-w-md border-border bg-surface p-6">
        <div className="mb-6 flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-accent/20 text-accent">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-foreground">Create FlowSentry account</h1>
            <p className="text-xs text-muted">Start monitoring workflow reliability & outcomes</p>
          </div>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <div>
            <label htmlFor="name" className="mb-1.5 block text-xs font-medium text-muted">
              Full name
            </label>
            <Input id="name" placeholder="Alex Rivera" {...register("name")} />
            {errors.name ? <p className="mt-1 text-xs text-red-400">{errors.name.message}</p> : null}
          </div>

          <div>
            <label htmlFor="email" className="mb-1.5 block text-xs font-medium text-muted">
              Work email
            </label>
            <Input id="email" type="email" placeholder="alex@agency.io" {...register("email")} />
            {errors.email ? (
              <p className="mt-1 text-xs text-red-400">{errors.email.message}</p>
            ) : null}
          </div>

          {AUTH_MODE === "supabase" ? (
            <div>
              <label htmlFor="password" className="mb-1.5 block text-xs font-medium text-muted">
                Password (min 8 chars)
              </label>
              <Input id="password" type="password" placeholder="••••••••" {...register("password")} />
            </div>
          ) : null}

          {serverError ? (
            <div className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
              {serverError}
            </div>
          ) : null}

          {infoMessage ? (
            <div className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">
              {infoMessage}
            </div>
          ) : null}

          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? "Creating account..." : "Create account"}
          </Button>
        </form>

        <div className="mt-5 border-t border-border pt-4 text-center text-xs text-muted">
          Already registered?{" "}
          <Link href="/login" className="text-accent hover:underline">
            Sign in
          </Link>
        </div>
      </Card>
    </div>
  );
}
