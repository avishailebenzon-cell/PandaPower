import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { env } from "@/lib/env";

interface SecurityLevel {
  id?: string;
  name: string;
  name_he: string;
  level: number;
  keywords: string[];
  description: string | null;
}

interface ClassificationResult {
  text_preview: string;
  detected_level: string;
  detected_level_number: number;
  matches: Record<
    string,
    { matched_keywords: string[]; match_count: number; level: number }
  >;
  total_matched_levels: number;
}

interface DefaultsStatus {
  has_user_defaults: boolean;
  saved_at: string | null;
  levels_count: number;
  total_keywords: number;
  source_for_reset: "user_saved" | "built_in";
}

// Color palette per level (1 = mild → 6 = critical)
const LEVEL_STYLES: Record<number, { bg: string; border: string; chip: string; text: string }> = {
  1: { bg: "bg-blue-900/20", border: "border-blue-700/50", chip: "bg-blue-900/40 border-blue-700 text-blue-200", text: "text-blue-300" },
  2: { bg: "bg-teal-900/20", border: "border-teal-700/50", chip: "bg-teal-900/40 border-teal-700 text-teal-200", text: "text-teal-300" },
  3: { bg: "bg-amber-900/20", border: "border-amber-700/50", chip: "bg-amber-900/40 border-amber-700 text-amber-200", text: "text-amber-300" },
  4: { bg: "bg-orange-900/20", border: "border-orange-700/50", chip: "bg-orange-900/40 border-orange-700 text-orange-200", text: "text-orange-300" },
  5: { bg: "bg-red-900/20", border: "border-red-700/50", chip: "bg-red-900/40 border-red-700 text-red-200", text: "text-red-300" },
  6: { bg: "bg-purple-900/30", border: "border-purple-700/50", chip: "bg-purple-900/40 border-purple-700 text-purple-200", text: "text-purple-300" },
};
const getStyle = (level: number) => LEVEL_STYLES[level] || LEVEL_STYLES[1];

function formatSavedAt(iso: string | null | undefined): string {
  if (!iso) return "מעולם לא נשמר";
  try {
    const d = new Date(iso);
    return d.toLocaleString("he-IL", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function SecurityClassificationPage() {
  const queryClient = useQueryClient();
  const [testText, setTestText] = useState("");
  const [testResult, setTestResult] = useState<ClassificationResult | null>(null);
  // newKeyword[levelName] = current input value for that level's "add" box
  const [newKeyword, setNewKeyword] = useState<Record<string, string>>({});

  const { data: levels } = useQuery<SecurityLevel[]>({
    queryKey: ["security-levels"],
    queryFn: () =>
      fetch(`${env.API_BASE_URL}/admin/security/levels`).then((r) => r.json()),
    refetchInterval: 30000,
  });

  // Tracks whether user-saved defaults exist + when they were saved
  const { data: defaultsStatus } = useQuery<DefaultsStatus>({
    queryKey: ["security-defaults-status"],
    queryFn: () =>
      fetch(`${env.API_BASE_URL}/admin/security/defaults-status`).then((r) => r.json()),
    refetchInterval: 30000,
  });

  // Add a single keyword to a level (inline, no modal)
  const addKeywordMutation = useMutation({
    mutationFn: async ({ levelName, keyword }: { levelName: string; keyword: string }) => {
      const res = await fetch(
        `${env.API_BASE_URL}/admin/security/levels/${encodeURIComponent(levelName)}/keywords/add`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ keyword }),
        }
      );
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },
    onSuccess: (_, vars) => {
      setNewKeyword((prev) => ({ ...prev, [vars.levelName]: "" }));
      queryClient.invalidateQueries({ queryKey: ["security-levels"] });
    },
  });

  // Remove a single keyword (click the × on a chip)
  const removeKeywordMutation = useMutation({
    mutationFn: async ({ levelName, keyword }: { levelName: string; keyword: string }) => {
      const res = await fetch(
        `${env.API_BASE_URL}/admin/security/levels/${encodeURIComponent(levelName)}/keywords/remove`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ keyword }),
        }
      );
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["security-levels"] }),
  });

  const testClassificationMutation = useMutation({
    mutationFn: (text: string) =>
      fetch(`${env.API_BASE_URL}/admin/security/test-classification`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      }).then((r) => r.json()),
    onSuccess: setTestResult,
  });

  const initDefaultsMutation = useMutation({
    mutationFn: () =>
      fetch(`${env.API_BASE_URL}/admin/security/initialize-defaults`, {
        method: "POST",
      }).then((r) => r.json()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["security-levels"] });
      queryClient.invalidateQueries({ queryKey: ["security-defaults-status"] });
    },
  });

  // Save current keywords as the new "factory defaults" (per this org).
  const saveAsDefaultsMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`${env.API_BASE_URL}/admin/security/save-as-defaults`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["security-defaults-status"] });
      alert(
        `✓ נשמר בהצלחה!\n\n` +
        `${data.levels_count} רמות, ${data.total_keywords} מילים נרדפות.\n` +
        `מעכשיו, כפתור "אפס לברירות מחדל" ישחזר את ההגדרות האלו.`
      );
    },
    onError: (err: Error) => {
      alert(`✗ שמירה נכשלה: ${err.message}`);
    },
  });

  const resetSavedDefaultsMutation = useMutation({
    mutationFn: () =>
      fetch(`${env.API_BASE_URL}/admin/security/reset-saved-defaults`, {
        method: "POST",
      }).then((r) => r.json()),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["security-defaults-status"] }),
  });

  const handleSaveAsDefaults = () => {
    const totalKw = levels?.reduce((s, l) => s + l.keywords.length, 0) ?? 0;
    const message =
      defaultsStatus?.has_user_defaults
        ? `האם להחליף את ברירות המחדל הקיימות (נשמרו ב-${formatSavedAt(defaultsStatus.saved_at)}) ` +
          `במצב הנוכחי (${levels?.length} רמות, ${totalKw} מילים נרדפות)?`
        : `האם לשמור את המצב הנוכחי (${levels?.length} רמות, ${totalKw} מילים נרדפות) ` +
          `כברירת המחדל של המערכת? מעכשיו "אפס לברירות מחדל" יחזיר את ההגדרות האלו.`;

    if (confirm(message)) {
      saveAsDefaultsMutation.mutate();
    }
  };

  const handleResetSavedDefaults = () => {
    if (
      confirm(
        "האם להסיר את ברירות המחדל ששמרת? מעכשיו 'אפס לברירות מחדל' יחזור להגדרות המקוריות של המערכת.\n\n" +
        "(הגדרות הצוות הנוכחיות נשארות כמו שהן - רק ה-snapshot נמחק.)"
      )
    ) {
      resetSavedDefaultsMutation.mutate();
    }
  };

  const handleAddKeyword = (levelName: string) => {
    const kw = (newKeyword[levelName] || "").trim();
    if (!kw) return;
    addKeywordMutation.mutate({ levelName, keyword: kw });
  };

  return (
    <div className="min-h-screen bg-gray-900 p-8" dir="rtl">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <div className="bg-gradient-to-r from-red-900 via-gray-800 to-purple-900 rounded-lg p-6 border border-gray-700">
            <h1 className="text-4xl font-bold text-white mb-2">🔒 ניהול סיווג ביטחוני</h1>
            <p className="text-red-200">
              הגדר מילים נרדפות (בעברית/אנגלית) לכל רמת סיווג.
              המערכת תזהה אוטומטית את הרמה הגבוהה ביותר שמופיעה בקורות החיים.
            </p>
          </div>
        </div>

        {/* Action Buttons + Defaults Status */}
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-4 mb-6">
          <div className="flex flex-wrap gap-3 items-center">
            {/* Save current as defaults */}
            <button
              onClick={handleSaveAsDefaults}
              disabled={saveAsDefaultsMutation.isPending || !levels?.length}
              className="px-4 py-2 bg-green-700 hover:bg-green-600 text-white rounded-lg disabled:opacity-50 font-semibold text-sm flex items-center gap-2"
              title="שמור את כל ההגדרות הנוכחיות כברירת המחדל של הצוות"
            >
              {saveAsDefaultsMutation.isPending ? "שומר..." : "💾 שמור כברירת מחדל"}
            </button>

            {/* Reset to saved (or built-in) defaults */}
            <button
              onClick={() => {
                if (
                  confirm(
                    defaultsStatus?.has_user_defaults
                      ? `האם לשחזר את ההגדרות ששמרתם ב-${formatSavedAt(defaultsStatus.saved_at)}?`
                      : "אין הגדרות שמורות. האם לטעון את ברירות המחדל המוטמעות במערכת?"
                  )
                ) {
                  initDefaultsMutation.mutate();
                }
              }}
              disabled={initDefaultsMutation.isPending}
              className="px-4 py-2 bg-purple-700 hover:bg-purple-600 text-white rounded-lg disabled:opacity-50 font-semibold text-sm flex items-center gap-2"
            >
              {initDefaultsMutation.isPending ? "מאתחל..." : "🔄 אפס לברירות מחדל"}
            </button>

            {/* Delete user-saved defaults (revert reset behavior to built-in) */}
            {defaultsStatus?.has_user_defaults && (
              <button
                onClick={handleResetSavedDefaults}
                disabled={resetSavedDefaultsMutation.isPending}
                className="px-3 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg disabled:opacity-50 text-xs"
                title="הסר את ההגדרות השמורות. 'אפס' יחזור לברירות מחדל מובנות במערכת"
              >
                🗑 הסר ברירות שמורות
              </button>
            )}

            <div className="text-xs text-gray-400 mr-auto">
              <div>
                סה"כ <span className="text-white font-semibold">{levels?.length ?? 0}</span> רמות,{" "}
                <span className="text-white font-semibold">
                  {levels?.reduce((s, l) => s + l.keywords.length, 0) ?? 0}
                </span>{" "}
                מילים נרדפות
              </div>
              {defaultsStatus && (
                <div className="mt-1">
                  {defaultsStatus.has_user_defaults ? (
                    <span className="text-green-400">
                      ✓ ברירת מחדל שמורה ({defaultsStatus.total_keywords} מילים) — נשמר{" "}
                      {formatSavedAt(defaultsStatus.saved_at)}
                    </span>
                  ) : (
                    <span className="text-amber-400">
                      ⚠ לא נשמרה ברירת מחדל. "אפס" יחזיר את הגדרות הברירת מחדל של המערכת.
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Test Classification - at top so user sees results immediately */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-6 mb-8">
          <h2 className="text-xl font-bold text-white mb-2">🧪 בדוק טקסט מקורות חיים</h2>
          <p className="text-xs text-gray-400 mb-4">
            הדבק קטע מ-CV ולחץ "בדוק" כדי לראות את הרמה שתזוהה אוטומטית.
          </p>

          <textarea
            value={testText}
            onChange={(e) => setTestText(e.target.value)}
            className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-gray-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm"
            rows={4}
            placeholder='לדוגמה: "שירות ביחידה 8200, סיווג רמה 4..."'
            dir="auto"
          />

          <div className="flex gap-2 mt-3">
            <button
              onClick={() => testClassificationMutation.mutate(testText)}
              disabled={!testText || testClassificationMutation.isPending}
              className="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg disabled:opacity-50 font-semibold text-sm"
            >
              {testClassificationMutation.isPending ? "מנתח..." : "🔍 בדוק סיווג"}
            </button>
            {testText && (
              <button
                onClick={() => { setTestText(""); setTestResult(null); }}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg text-sm"
              >
                נקה
              </button>
            )}
          </div>

          {testResult && (
            <div className="mt-5 pt-5 border-t border-gray-700">
              <div className="grid grid-cols-3 gap-3 mb-4">
                <div className={`p-4 rounded-lg border ${testResult.detected_level_number > 0 ? getStyle(testResult.detected_level_number).bg + " " + getStyle(testResult.detected_level_number).border : "bg-gray-900 border-gray-700"}`}>
                  <div className="text-xs text-gray-400">רמה שזוהתה</div>
                  <div className={`text-2xl font-bold ${testResult.detected_level_number > 0 ? getStyle(testResult.detected_level_number).text : "text-gray-400"}`}>
                    {testResult.detected_level}
                  </div>
                </div>
                <div className="bg-gray-900 p-4 rounded-lg border border-gray-700">
                  <div className="text-xs text-gray-400">מספר רמה</div>
                  <div className="text-2xl font-bold text-white">{testResult.detected_level_number}</div>
                </div>
                <div className="bg-gray-900 p-4 rounded-lg border border-gray-700">
                  <div className="text-xs text-gray-400">רמות שהתאימו</div>
                  <div className="text-2xl font-bold text-white">{testResult.total_matched_levels}</div>
                </div>
              </div>

              {Object.keys(testResult.matches).length > 0 ? (
                <div className="space-y-2">
                  {Object.entries(testResult.matches).map(([levelName, data]) => {
                    const style = getStyle(data.level);
                    return (
                      <div key={levelName} className={`p-3 rounded border ${style.bg} ${style.border}`}>
                        <div className={`font-bold ${style.text} mb-1`}>{levelName}</div>
                        <div className="flex flex-wrap gap-1">
                          {data.matched_keywords.map((kw) => (
                            <span key={kw} className={`text-xs px-2 py-0.5 rounded-full border ${style.chip}`}>
                              {kw}
                            </span>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="bg-gray-900 p-4 rounded text-center text-gray-400 text-sm">
                  לא נמצאו התאמות — הטקסט יסווג כ"לא מסווג"
                </div>
              )}
            </div>
          )}
        </div>

        {/* Security Levels Grid - 2 columns */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {levels?.map((level) => {
            const style = getStyle(level.level);
            const isAdding = addKeywordMutation.isPending && addKeywordMutation.variables?.levelName === level.name;
            return (
              <div
                key={level.name}
                className={`p-5 rounded-lg border-2 ${style.bg} ${style.border}`}
              >
                {/* Level header */}
                <div className="flex justify-between items-start mb-3">
                  <div>
                    <h3 className={`text-xl font-bold ${style.text}`}>
                      {level.name_he}
                    </h3>
                    <p className="text-xs text-gray-400 font-mono">{level.name}</p>
                    {level.description && (
                      <p className="text-xs text-gray-300 mt-1">{level.description}</p>
                    )}
                  </div>
                  <div className={`px-3 py-1 rounded-lg font-bold text-lg ${style.chip}`}>
                    L{level.level}
                  </div>
                </div>

                {/* Keywords chips with delete-on-click */}
                <div className="mb-3">
                  <div className="text-xs text-gray-400 font-semibold mb-2">
                    מילים נרדפות ({level.keywords.length})
                  </div>
                  <div className="flex flex-wrap gap-1.5 min-h-[2rem]">
                    {level.keywords.length === 0 ? (
                      <span className="text-xs text-gray-500 italic">אין מילים נרדפות. הוסף למטה ↓</span>
                    ) : (
                      level.keywords.map((kw) => (
                        <span
                          key={kw}
                          className={`group inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-mono border ${style.chip}`}
                        >
                          <span dir="auto">{kw}</span>
                          <button
                            onClick={() =>
                              removeKeywordMutation.mutate({
                                levelName: level.name,
                                keyword: kw,
                              })
                            }
                            className="opacity-50 hover:opacity-100 hover:text-red-400 transition-opacity text-sm leading-none"
                            title={`הסר "${kw}"`}
                          >
                            ×
                          </button>
                        </span>
                      ))
                    )}
                  </div>
                </div>

                {/* Add keyword inline */}
                <div className="flex gap-2 pt-3 border-t border-gray-700/50">
                  <input
                    type="text"
                    value={newKeyword[level.name] || ""}
                    onChange={(e) =>
                      setNewKeyword((prev) => ({ ...prev, [level.name]: e.target.value }))
                    }
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        handleAddKeyword(level.name);
                      }
                    }}
                    placeholder="הוסף מילה נרדפת (עברית או אנגלית)"
                    className="flex-1 px-3 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    dir="auto"
                  />
                  <button
                    onClick={() => handleAddKeyword(level.name)}
                    disabled={!newKeyword[level.name]?.trim() || isAdding}
                    className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-sm font-semibold disabled:opacity-50"
                  >
                    {isAdding ? "..." : "+ הוסף"}
                  </button>
                </div>
              </div>
            );
          })}
        </div>

        {/* Help block */}
        <div className="mt-8 bg-gray-800 border border-gray-700 rounded-lg p-5 text-sm text-gray-300">
          <h3 className="font-bold text-white mb-2">💡 איך זה עובד</h3>
          <ul className="space-y-1 list-disc list-inside text-xs text-gray-400">
            <li>בכל פעם שמגיע CV חדש, Claude מקבל את הרשימה הזו ומחפש את המילים בטקסט.</li>
            <li>אם מתגלה התאמה במספר רמות, נבחרת הרמה הגבוהה ביותר.</li>
            <li>אפשר להוסיף וריאציות כמו "סיווג רמה 4", "Level 4", "ביטחוני 4" — והמערכת תזהה את כולן.</li>
            <li>כדי להסיר מילה — לחץ על ה־× בצ'יפ שלה.</li>
            <li>שינויים נכנסים לתוקף מיד עבור CVs חדשים שמתעבדים.</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
