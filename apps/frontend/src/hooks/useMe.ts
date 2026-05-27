import { useQuery } from "@tanstack/react-query";
import { useAuth } from "./useAuth";

// Internal admin tool - returns admin role without backend round-trip.
// TODO: Wire up real /api/me once backend exposes it and real auth lands.
export function useMe() {
  const { user, loading: authLoading } = useAuth();

  return useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      return { email: user?.email || "admin@test.com", role: "admin" };
    },
    enabled: !!user && !authLoading,
    staleTime: 5 * 60 * 1000,
  });
}
