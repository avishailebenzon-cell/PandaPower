import { useQuery } from "@tanstack/react-query";
import { useAuth } from "./useAuth";
import { env } from "@/lib/env";

export function useMe() {
  const { user, loading: authLoading } = useAuth();

  return useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      if (import.meta.env.DEV && user?.email === "admin@test.com") {
        return { email: user.email, role: "admin" };
      }
      const response = await fetch(`${env.API_BASE_URL}/api/me`);
      if (!response.ok) throw new Error("Failed to fetch user profile");
      return response.json();
    },
    enabled: !!user && !authLoading,
    staleTime: 5 * 60 * 1000,
  });
}
