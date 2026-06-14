import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { env } from "@/lib/env";

interface AlertsConfig {
  admin_email: string;
  enabled: boolean;
}

interface AcknowledgedKey {
  key: string;
  expires_at: string;
}

interface AlertsStatus extends AlertsConfig {
  cooldown_minutes: number;
  max_alerts_per_hour: number;
  recent_alerts_count: number;
  active_cooldowns: { key: string; remaining_seconds: number }[];
  snoozed_until: string | null;
  acknowledged_keys: AcknowledgedKey[];
}

interface AlertPreferences {
  enabled: boolean;
  min_interval_minutes: number;
  channels: Record<string, boolean>;
  categories: Record<string, boolean>;
  channel_labels: Record<string, string>;
  category_labels: Record<string, string>;
}

// Human-friendly labels for the alert keys the pipeline emits.
const ALERT_KEY_LABELS: Record<string, string> = {
  "pipeline-ingest-repeated-failures": "סריקת מיילים נכשלה ברציפות",
  "pipeline-parse-repeated-failures": "ניתוח CV נכשל ברציפות",
  "pipeline-candidates-repeated-failures": "יצירת מועמדים נכשלה ברציפות",
  "pipeline-skills-repeated-failures": "נורמליזציית כישורים נכשלה ברציפות",
  "pipeline-ingest-crash": "קריסה בסריקת מיילים",
  "pipeline-parse-crash": "קריסה בניתוח CV",
  "pipeline-candidates-crash": "קריסה ביצירת מועמדים",
  "pipeline-skills-crash": "קריסה בנורמליזציית כישורים",
};

function labelForKey(key: string): string {
  return ALERT_KEY_LABELS[key] || key;
}

function formatRelativeTime(iso: string): string {
  const ts = new Date(iso).getTime();
  const diff = ts - Date.now();
  if (diff <= 0) return "פג";
  // 100-year sentinel = "indefinite"
  if (diff > 50 * 365 * 24 * 3600 * 1000) return "ללא תוקף (עד ביטול ידני)";
  const mins = Math.round(diff / 60000);
  if (mins < 60) return `${mins} דק'`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} שעות`;
  const days = Math.round(hours / 24);
  return `${days} ימים`;
}

interface TestResult {
  sent: boolean;
  recipient?: string;
  error?: string;
}

export function AlertsPage() {
  const queryClient = useQueryClient();
  const [emailInput, setEmailInput] = useState("");
  const [testTo, setTestTo] = useState("");
  const [lastTestResult, setLastTestResult] = useState<TestResult | null>(null);

  const { data: status } = useQuery<AlertsStatus>({
    queryKey: ["alerts-status"],
    queryFn: () =>
      fetch(`${env.API_BASE_URL}/admin/alerts/status`).then((r) => r.json()),
    refetchInterval: 10000,
  });

  // Pre-fill the email input once when we first load the status
  useEffect(() => {
    if (status?.admin_email && !emailInput) {
      setEmailInput(status.admin_email);
    }
  }, [status?.admin_email]); // eslint-disable-line react-hooks/exhaustive-deps

  const updateConfigMutation = useMutation({
    mutationFn: async (body: Partial<AlertsConfig>) => {
      const res = await fetch(`${env.API_BASE_URL}/admin/alerts/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Update failed");
      return res.json();
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts-status"] }),
  });

  // ── Granular alert preferences (channels / categories / interval) ──────
  const { data: prefs } = useQuery<AlertPreferences>({
    queryKey: ["alerts-preferences"],
    queryFn: () =>
      fetch(`${env.API_BASE_URL}/admin/alerts/preferences`).then((r) => r.json()),
    refetchInterval: 30000,
  });

  const updatePrefsMutation = useMutation({
    mutationFn: async (body: Partial<AlertPreferences>) => {
      const res = await fetch(`${env.API_BASE_URL}/admin/alerts/preferences`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Update failed");
      return res.json();
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts-preferences"] }),
  });

  const testMutation = useMutation({
    mutationFn: async (to: string | null) => {
      const url = to
        ? `${env.API_BASE_URL}/admin/alerts/test?to=${encodeURIComponent(to)}`
        : `${env.API_BASE_URL}/admin/alerts/test`;
      const res = await fetch(url, { method: "POST" });
      return (await res.json()) as TestResult;
    },
    onSuccess: setLastTestResult,
    onError: (e: Error) => setLastTestResult({ sent: false, error: e.message }),
  });

  // ── Snooze + Acknowledge mutations ─────────────────────────────────────

  const snoozeMutation = useMutation({
    mutationFn: async (minutes: number) => {
      const res = await fetch(`${env.API_BASE_URL}/admin/alerts/snooze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ minutes }),
      });
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts-status"] }),
  });

  const unsnoozeMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`${env.API_BASE_URL}/admin/alerts/unsnooze`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts-status"] }),
  });

  const acknowledgeMutation = useMutation({
    mutationFn: async ({ key, minutes }: { key: string; minutes: number }) => {
      const res = await fetch(`${env.API_BASE_URL}/admin/alerts/acknowledge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key, minutes }),
      });
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts-status"] }),
  });

  const unacknowledgeMutation = useMutation({
    mutationFn: async (key: string) => {
      const res = await fetch(`${env.API_BASE_URL}/admin/alerts/unacknowledge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key, minutes: 0 }),
      });
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts-status"] }),
  });

  const handleSaveEmail = () => {
    if (!emailInput.trim()) return;
    updateConfigMutation.mutate({ admin_email: emailInput.trim() });
  };

  const handleToggleEnabled = () => {
    if (!status) return;
    updateConfigMutation.mutate({ enabled: !status.enabled });
  };

  return (
    <div className="min-h-screen bg-gray-900 p-8" dir="rtl">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <div className="bg-gradient-to-r from-red-900 via-gray-800 to-amber-900 rounded-lg p-6 border border-gray-700">
            <h1 className="text-4xl font-bold text-white mb-2">🔔 התראות מערכת</h1>
            <p className="text-amber-200">
              הגדר למי לשלוח דוא"ל אוטומטית כשהתגלות תקלות בסריקת המיילים, ניתוח ה-CVs או רכיב אחר.
            </p>
            <p className="text-xs text-amber-200/70 mt-2">
              ⚡ נשלח דרך <a href="https://resend.com" target="_blank" rel="noopener" className="underline">Resend</a>.
              נדרש <code className="bg-black/30 px-1 rounded">RESEND_API_KEY</code> ב-<code className="bg-black/30 px-1 rounded">.env</code>.
            </p>
          </div>
        </div>

        {/* ── Alert preferences: master / interval / channels / categories ── */}
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 mb-6">
          <h2 className="text-xl font-bold text-white mb-1">⚙️ הגדרות התראות</h2>
          <p className="text-xs text-gray-400 mb-4">
            שליטה מלאה: הפעלה כללית, תדירות מקסימלית, ובחירה לפי ערוץ (מייל / בוט) ולפי סוג התראה.
          </p>

          {/* Master switch */}
          <div className="flex items-center justify-between py-3 border-b border-gray-700">
            <div>
              <div className="text-white font-semibold">התראות פעילות (מתג ראשי)</div>
              <div className="text-xs text-gray-400">כשכבוי — לא נשלחות התראות בכלל.</div>
            </div>
            <ToggleSwitch
              on={!!prefs?.enabled}
              onChange={(v) => updatePrefsMutation.mutate({ enabled: v })}
            />
          </div>

          {/* Global interval */}
          <div className="flex items-center justify-between py-3 border-b border-gray-700">
            <div>
              <div className="text-white font-semibold">תדירות מקסימלית</div>
              <div className="text-xs text-gray-400">לכל היותר התראה אחת אחת לכל פרק זמן זה.</div>
            </div>
            <div className="flex items-center gap-2">
              {[
                { label: "6 שעות", v: 360 },
                { label: "12 שעות", v: 720 },
                { label: "24 שעות", v: 1440 },
              ].map((opt) => (
                <button
                  key={opt.v}
                  onClick={() => updatePrefsMutation.mutate({ min_interval_minutes: opt.v })}
                  className={`px-3 py-1.5 rounded text-sm font-semibold transition ${
                    prefs?.min_interval_minutes === opt.v
                      ? "bg-indigo-600 text-white"
                      : "bg-gray-700 text-gray-300 hover:bg-gray-600"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
              <span className="text-xs text-gray-500">({prefs?.min_interval_minutes ?? "—"} דק')</span>
            </div>
          </div>

          {/* Channels */}
          <div className="py-3 border-b border-gray-700">
            <div className="text-white font-semibold mb-2">ערוצי שליחה</div>
            {prefs && Object.keys(prefs.channels).map((ch) => (
              <div key={ch} className="flex items-center justify-between py-1.5">
                <span className="text-gray-200 text-sm">{prefs.channel_labels[ch] || ch}</span>
                <ToggleSwitch
                  on={prefs.channels[ch]}
                  onChange={(v) => updatePrefsMutation.mutate({ channels: { [ch]: v } })}
                />
              </div>
            ))}
          </div>

          {/* Categories */}
          <div className="py-3">
            <div className="text-white font-semibold mb-2">סוגי התראות</div>
            {prefs && Object.keys(prefs.categories).map((cat) => (
              <div key={cat} className="flex items-center justify-between py-1.5">
                <span className="text-gray-200 text-sm">{prefs.category_labels[cat] || cat}</span>
                <ToggleSwitch
                  on={prefs.categories[cat]}
                  onChange={(v) => updatePrefsMutation.mutate({ categories: { [cat]: v } })}
                />
              </div>
            ))}
          </div>
        </div>

        {/* ── Snooze panel: "I saw the problem, stop emailing me about it" ── */}
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 mb-6">
          <div className="flex items-start justify-between mb-3">
            <div>
              <h2 className="text-xl font-bold text-white">⏸ עצירת שליחה זמנית</h2>
              <p className="text-xs text-gray-400 mt-1">
                ראית את הבעיה ואתה מטפל בה? עצור זמנית את שליחת המיילים כדי לא לקבל יותר התראות עד שתסיים.
              </p>
            </div>
            {status?.snoozed_until && (
              <span className="text-xs bg-amber-900/40 text-amber-200 border border-amber-700 px-3 py-1 rounded-full font-semibold whitespace-nowrap">
                🔕 מושתק כרגע
              </span>
            )}
          </div>

          {status?.snoozed_until ? (
            // SNOOZED state - show resume button + countdown
            <div className="bg-amber-900/20 border border-amber-700 rounded p-4">
              <div className="flex items-center justify-between gap-4">
                <div className="text-sm text-amber-100">
                  <div className="font-semibold mb-1">כל ההתראות מושתקות</div>
                  <div className="text-xs text-amber-200/80">
                    יחזרו אוטומטית בעוד <span className="font-bold">{formatRelativeTime(status.snoozed_until)}</span>
                    {" · "}
                    <span className="text-amber-200/60">
                      ({new Date(status.snoozed_until).toLocaleString("he-IL")})
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => unsnoozeMutation.mutate()}
                  disabled={unsnoozeMutation.isPending}
                  className="px-4 py-2 bg-green-700 hover:bg-green-600 disabled:opacity-50 text-white font-semibold rounded text-sm whitespace-nowrap"
                >
                  {unsnoozeMutation.isPending ? "..." : "▶ חדש שליחה"}
                </button>
              </div>
            </div>
          ) : (
            // NOT snoozed - show quick-snooze buttons
            <div className="flex flex-wrap gap-2">
              {[
                { mins: 60, label: "שעה" },
                { mins: 4 * 60, label: "4 שעות" },
                { mins: 24 * 60, label: "24 שעות" },
                { mins: 0, label: "עד ביטול ידני" },
              ].map((opt) => (
                <button
                  key={opt.mins}
                  onClick={() => {
                    if (
                      opt.mins === 0 &&
                      !confirm(
                        "השתק את כל ההתראות ללא תוקף? לא יישלחו מיילים כלל עד שתלחץ 'חדש שליחה'."
                      )
                    ) {
                      return;
                    }
                    snoozeMutation.mutate(opt.mins);
                  }}
                  disabled={snoozeMutation.isPending}
                  className="px-4 py-2 bg-amber-700 hover:bg-amber-600 disabled:opacity-50 text-white text-sm font-semibold rounded"
                >
                  🔕 השתק ל-{opt.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* ── Acknowledged alerts list ── (only shown if there are any) */}
        {status && status.acknowledged_keys.length > 0 && (
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 mb-6">
            <h2 className="text-xl font-bold text-white mb-1">✓ התראות מוכרות</h2>
            <p className="text-xs text-gray-400 mb-4">
              אלו התראות שסימנת כ"ראיתי, אטפל". לא יישלחו מיילים עליהן עד שתבטל את הסימון או עד שיפוג התוקף.
            </p>
            <div className="space-y-2">
              {status.acknowledged_keys.map((ack) => (
                <div
                  key={ack.key}
                  className="flex items-center justify-between bg-gray-900 border border-gray-700 rounded p-3"
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold text-white">{labelForKey(ack.key)}</div>
                    <div className="text-xs text-gray-400 font-mono mt-0.5">{ack.key}</div>
                    <div className="text-xs text-amber-300 mt-1">
                      🔕 מושתק עוד {formatRelativeTime(ack.expires_at)}
                    </div>
                  </div>
                  <button
                    onClick={() => unacknowledgeMutation.mutate(ack.key)}
                    disabled={unacknowledgeMutation.isPending}
                    className="px-3 py-1.5 bg-gray-700 hover:bg-green-700 text-gray-200 text-xs font-semibold rounded whitespace-nowrap"
                    title="הסר השתקה - התראות יחזרו לעבוד עבור הkey הזה"
                  >
                    ↻ חדש שליחה
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Main Config Card */}
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-bold text-white">הגדרות</h2>
            {status && (
              <button
                onClick={handleToggleEnabled}
                disabled={updateConfigMutation.isPending}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg font-semibold text-sm transition-colors ${
                  status.enabled
                    ? "bg-green-900/40 text-green-200 border border-green-700 hover:bg-green-900/60"
                    : "bg-gray-700 text-gray-300 border border-gray-600 hover:bg-gray-600"
                }`}
              >
                {status.enabled ? "✓ פעיל - התראות יישלחו" : "✕ כבוי - לא יישלחו התראות"}
              </button>
            )}
          </div>

          <div className="space-y-3">
            <label className="block text-sm text-gray-300 font-semibold">
              כתובת דוא"ל של מנהל המערכת
            </label>
            <p className="text-xs text-gray-400 -mt-1">
              כל מיילי המערכת נשלחים לכתובת זו — התראות תקלות, וגם התראות הסוכנים
              (לקוח חדש של ליבי, פניות מועמדים וכו'). שינוי כאן משפיע על הכול.
            </p>
            <div className="flex gap-2">
              <input
                type="email"
                value={emailInput}
                onChange={(e) => setEmailInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSaveEmail()}
                placeholder="admin@company.com"
                className="flex-1 px-3 py-2 bg-gray-900 border border-gray-700 rounded text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-amber-500"
                dir="ltr"
              />
              <button
                onClick={handleSaveEmail}
                disabled={
                  updateConfigMutation.isPending ||
                  !emailInput.trim() ||
                  emailInput.trim() === status?.admin_email
                }
                className="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white font-semibold rounded text-sm"
              >
                {updateConfigMutation.isPending ? "..." : "💾 שמור"}
              </button>
            </div>
            {status && emailInput.trim() !== status.admin_email && (
              <p className="text-xs text-amber-400">
                ⚠ לא נשמר עדיין — הכתובת הנוכחית: <code>{status.admin_email}</code>
              </p>
            )}
          </div>
        </div>

        {/* Test Alert */}
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 mb-6">
          <h2 className="text-xl font-bold text-white mb-3">🧪 בדוק שליחה</h2>
          <p className="text-xs text-gray-400 mb-4">
            שלח דוא"ל ניסיון כדי לוודא ש-Resend מוגדר נכון. ניתן להזין כתובת ספציפית או להשתמש בכתובת המנהל.
          </p>

          <div className="flex gap-2 mb-3">
            <input
              type="email"
              value={testTo}
              onChange={(e) => setTestTo(e.target.value)}
              placeholder={`להשתמש בכתובת הקבועה (${status?.admin_email || "?"})`}
              className="flex-1 px-3 py-2 bg-gray-900 border border-gray-700 rounded text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-amber-500"
              dir="ltr"
            />
            <button
              onClick={() => testMutation.mutate(testTo.trim() || null)}
              disabled={testMutation.isPending}
              className="px-5 py-2 bg-amber-700 hover:bg-amber-600 disabled:opacity-40 text-white font-semibold rounded text-sm"
            >
              {testMutation.isPending ? "שולח..." : "📨 שלח דוא\"ל ניסיון"}
            </button>
          </div>

          {lastTestResult && (
            <div
              className={`rounded p-4 border text-sm ${
                lastTestResult.sent
                  ? "bg-green-900/20 border-green-700 text-green-200"
                  : "bg-red-900/20 border-red-700 text-red-200"
              }`}
            >
              {lastTestResult.sent ? (
                <>
                  <div className="font-bold mb-1">✓ דוא"ל נשלח בהצלחה!</div>
                  <div className="text-xs">
                    נשלח אל: <code>{lastTestResult.recipient}</code>. בדוק את תיבת ה-Inbox (וגם את ה-Spam).
                  </div>
                </>
              ) : (
                <>
                  <div className="font-bold mb-1">✗ שליחה נכשלה</div>
                  <div className="text-xs whitespace-pre-wrap break-words font-mono">
                    {lastTestResult.error}
                  </div>
                  {/* Common diagnosis: RESEND_API_KEY missing */}
                  {lastTestResult.error?.includes("RESEND_API_KEY") && (
                    <div className="mt-3 pt-3 border-t border-red-700 text-xs text-red-100">
                      <div className="font-semibold mb-1">💡 איך לתקן:</div>
                      <ol className="list-decimal list-inside space-y-1 mr-2">
                        <li>היכנס ל-<a href="https://resend.com/api-keys" target="_blank" rel="noopener" className="underline">resend.com/api-keys</a></li>
                        <li>צור API key חדש (או השתמש בקיים)</li>
                        <li>פתח את <code className="bg-red-900/40 px-1 rounded">apps/backend/.env</code></li>
                        <li>הוסף שורה: <code className="bg-red-900/40 px-1 rounded">RESEND_API_KEY=re_...</code></li>
                        <li>הפעל מחדש את ה-backend (uvicorn) — וזהו</li>
                      </ol>
                    </div>
                  )}
                  {/* Resend API errors (invalid key, domain not verified, etc.) */}
                  {lastTestResult.error?.includes("Resend API") && (
                    <div className="mt-3 pt-3 border-t border-red-700 text-xs text-red-100">
                      <div className="font-semibold mb-1">💡 בדיקות נפוצות:</div>
                      <ul className="list-disc list-inside space-y-1 mr-2">
                        <li>ודא ש-RESEND_API_KEY ב-.env תקין ומתחיל ב-<code className="bg-red-900/40 px-1 rounded">re_</code></li>
                        <li>אם השגיאה היא "from address not verified" — ודא שהדומיין מאומת ב-Resend, או הסר את ההגדרה כדי להשתמש ב-onboarding sender המוגדר מראש</li>
                        <li>אם השגיאה היא 401/403 — ה-API key לא תקף או נמחק</li>
                      </ul>
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </div>

        {/* Diagnostics */}
        {status && (
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 mb-6">
            <h2 className="text-xl font-bold text-white mb-4">📊 דיאגנוסטיקה</h2>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
              <div className="bg-gray-900 p-3 rounded border border-gray-700">
                <div className="text-xs text-gray-400">Cooldown</div>
                <div className="text-xl font-bold text-white">{status.cooldown_minutes} דק'</div>
                <div className="text-[10px] text-gray-500 mt-1">פעם בין התראות זהות</div>
              </div>
              <div className="bg-gray-900 p-3 rounded border border-gray-700">
                <div className="text-xs text-gray-400">תקרה שעתית</div>
                <div className="text-xl font-bold text-white">{status.max_alerts_per_hour}</div>
                <div className="text-[10px] text-gray-500 mt-1">מקסימום דוא"לים/שעה</div>
              </div>
              <div className="bg-gray-900 p-3 rounded border border-gray-700">
                <div className="text-xs text-gray-400">נשלחו (60 דק' אחרונות)</div>
                <div className="text-xl font-bold text-amber-300">{status.recent_alerts_count}</div>
              </div>
              <div className="bg-gray-900 p-3 rounded border border-gray-700">
                <div className="text-xs text-gray-400">בcooldown כעת</div>
                <div className="text-xl font-bold text-blue-300">{status.active_cooldowns.length}</div>
              </div>
            </div>

            {status.active_cooldowns.length > 0 && (
              <div>
                <h3 className="text-sm font-bold text-gray-200 mb-2">התראות בcooldown</h3>
                <div className="space-y-1">
                  {status.active_cooldowns.map((cd) => (
                    <div
                      key={cd.key}
                      className="flex justify-between items-center bg-gray-900 px-3 py-2 rounded text-xs border border-gray-700"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="font-semibold text-gray-200">{labelForKey(cd.key)}</div>
                        <code className="text-amber-300 text-[10px]">{cd.key}</code>
                      </div>
                      <span className="text-gray-400 mx-3">
                        תיבדק שוב בעוד{" "}
                        <span className="text-white font-semibold">
                          {Math.floor(cd.remaining_seconds / 60)} דק'{" "}
                          {cd.remaining_seconds % 60} שנ'
                        </span>
                      </span>
                      <button
                        onClick={() => {
                          if (
                            confirm(
                              `סמן "${labelForKey(cd.key)}" כמוכר.\n\n` +
                              `לא יישלחו מיילים נוספים על הבעיה הזו עד שתבטל את הסימון.`
                            )
                          ) {
                            acknowledgeMutation.mutate({ key: cd.key, minutes: 0 });
                          }
                        }}
                        disabled={acknowledgeMutation.isPending}
                        className="px-2 py-1 bg-gray-700 hover:bg-green-700 text-gray-200 rounded text-[11px] font-semibold whitespace-nowrap"
                        title="סמן כראיתי - לא לשלוח עוד עליה"
                      >
                        ✓ ראיתי
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* What triggers alerts */}
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
          <h2 className="text-xl font-bold text-white mb-3">⚠ מתי תקבל התראה?</h2>
          <p className="text-sm text-gray-400 mb-4">
            המערכת שולחת התראה רק כשמשהו נכשל <strong>פעמיים או יותר ברציפות</strong> — לא על
            כשלון בודד. זה מונע ספאם בשעות שיא, ומתריע רק כשיש בעיה ממשית.
          </p>

          <div className="space-y-3 text-sm">
            <div className="flex items-start gap-3 bg-gray-900 p-3 rounded border border-gray-700">
              <span className="text-2xl">📥</span>
              <div>
                <div className="font-semibold text-white">סריקת מיילים נכשלה 3+ פעמים</div>
                <div className="text-xs text-gray-400">
                  Azure לא מגיב, אימות נכשל, או שיש שגיאת רשת מתמשכת.
                </div>
              </div>
            </div>
            <div className="flex items-start gap-3 bg-gray-900 p-3 rounded border border-gray-700">
              <span className="text-2xl">🤖</span>
              <div>
                <div className="font-semibold text-white">ניתוח CVs נתקע 3+ פעמים</div>
                <div className="text-xs text-gray-400">
                  Claude API לא משיב, חרוג תקציב, או JSON לא תקין מסיבה כלשהי.
                </div>
              </div>
            </div>
            <div className="flex items-start gap-3 bg-gray-900 p-3 rounded border border-gray-700">
              <span className="text-2xl">👥</span>
              <div>
                <div className="font-semibold text-white">יצירת מועמדים נתקעת</div>
                <div className="text-xs text-gray-400">
                  שדה חובה חסר, או בעיית סכמה ב-DB.
                </div>
              </div>
            </div>
            <div className="flex items-start gap-3 bg-gray-900 p-3 rounded border border-gray-700">
              <span className="text-2xl">💥</span>
              <div>
                <div className="font-semibold text-white">קריסה של pipeline scheduler</div>
                <div className="text-xs text-gray-400">
                  באג בקוד שגורם לexception בלולאה הראשית — נכלל ב-traceback בדוא"ל.
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ToggleSwitch({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!on)}
      role="switch"
      aria-checked={on}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
        on ? "bg-green-600" : "bg-gray-600"
      }`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
          on ? "translate-x-1" : "translate-x-6"
        }`}
      />
    </button>
  );
}
