"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { LoadingState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";

export default function HomePage() {
  const router = useRouter();
  const { user, isLoading } = useAuth();

  useEffect(() => {
    if (!isLoading) {
      router.replace(user ? "/overview" : "/login");
    }
  }, [isLoading, user, router]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-sm">
        <LoadingState label="Loading FlowSentry..." />
      </div>
    </div>
  );
}
