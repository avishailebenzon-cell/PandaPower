import { useState } from "react";

// Internal admin tool - no public-facing auth implemented yet.
// Auto-logs in as admin in both dev AND production (this is an internal tool).
// TODO: Replace with real Supabase Auth + LoginPage when public users are added.
export function useAuth() {
  const [user] = useState({ email: "admin@test.com", user_metadata: { role: "admin" } });
  const [loading] = useState(false);
  const [error] = useState(null);

  return { user, loading, error };
}
