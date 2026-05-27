const getEnv = (key, fallback) => {
    const value = import.meta.env[`VITE_${key}`];
    if (!value && !fallback) {
        throw new Error(`Missing environment variable: VITE_${key}`);
    }
    return value || fallback || "";
};
export const env = {
    SUPABASE_URL: getEnv("SUPABASE_URL"),
    SUPABASE_ANON_KEY: getEnv("SUPABASE_ANON_KEY"),
    API_BASE_URL: getEnv("API_URL", "http://localhost:8000"),
};
