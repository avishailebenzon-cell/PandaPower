import { createClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

let supabase;

if (supabaseUrl && supabaseAnonKey) {
  supabase = createClient(supabaseUrl, supabaseAnonKey);
} else if (import.meta.env.DEV) {
  supabase = createClient("https://placeholder.supabase.co", "placeholder-key");
} else {
  throw new Error("Missing Supabase environment variables");
}

export { supabase };
