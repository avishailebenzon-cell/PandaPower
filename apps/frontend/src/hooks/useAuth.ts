import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";

export function useAuth() {
  const [user, setUser] = useState(
    import.meta.env.DEV ? { email: "admin@test.com", user_metadata: { role: "admin" } } : null
  );
  const [loading, setLoading] = useState(!import.meta.env.DEV);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (import.meta.env.DEV) {
      setLoading(false);
      return;
    }

    const getSession = async () => {
      try {
        const { data } = await supabase.auth.getSession();
        setUser(data.session?.user || null);
      } catch (err) {
        setError(err);
      } finally {
        setLoading(false);
      }
    };

    getSession();

    const { data: listener } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        setUser(session?.user || null);
      }
    );

    return () => {
      listener?.subscription.unsubscribe();
    };
  }, []);

  return { user, loading, error };
}
