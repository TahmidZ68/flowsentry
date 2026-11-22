import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";

export const AUTH_MODE = (process.env.NEXT_PUBLIC_AUTH_MODE || "local_dev") as "supabase" | "local_dev";

let cachedClient: SupabaseClient | null = null;

export function getSupabaseClient(): SupabaseClient | null {
  if (!supabaseUrl || !supabaseAnonKey) return null;
  if (!cachedClient) {
    cachedClient = createClient(supabaseUrl, supabaseAnonKey);
  }
  return cachedClient;
}
