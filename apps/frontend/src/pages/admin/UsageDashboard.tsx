import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";

// CRITICAL: Get API base URL from environment - MUST use VITE_API_URL (not VITE_API_BASE)
const API_BASE = import.meta.env.VITE_API_URL || "";

interface Bucket {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
}

interface StageBucket extends Bucket {
  stage: string;
  label: string;
}

interface ModelBucket extends Bucket {
  model: string;
}

interface DayBucket extends Bucket {
  day: string;
}

interface UsageSummary {
  days: number;
  since: string | null;
  truncated: boolean;
  totals: Bucket;
  by_stage: StageBucket[];
  by_model: ModelBucket[];
  by_day: DayBucket[];
  note?: string;
}

const fetchUsage = async (days: number): Promise<UsageSummary> => {
  const response = await fetch(`${API_BASE}/admin/usage/summary?days=${days}`);
  if (!response.ok) throw new Error("Failed to fetch usage summary");
  return response.json();
};

interface UnitCosts {
  cost_per_cv_usd: number;
  cost_per_match_usd: number;
  counts: { cv_parses: number; convertapi_conversions: number; match_evaluations: number };
  components: { cv_parse_usd: number; convertapi_usd: number; agent_match_usd: number; other_usd: number };
  total_cost_usd: number;
  note?: string;
}

const fetchUnitCosts = async (days: number): Promise<UnitCosts> => {
  const response = await fetch(`${API_BASE}/admin/usage/unit-costs?days=${days}`);
  if (!response.ok) throw new Error("Failed to fetch unit costs");
  return response.json();
};

function fmtUsd4(n: number): string {
  return `$${(n || 0).toFixed(4)}`;
}

function fmtNum(n: number): string {
  return new Intl.NumberFormat("he-IL").format(Math.round(n || 0));
}

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return fmtNum(n);
}

function fmtUsd(n: number): string {
  return `$${(n || 0).toFixed(2)}`;
}

// Stable-ish color per stage for the cost bars.
const STAGE_COLORS: Record<string, string> = {
  cv_parse: "bg-emerald-500",
  agent_match: "bg-amber-500",
  pandi_conversation: "bg-rose-500",
  pandi_moderation: "bg-purple-500",
  unknown: "bg-slate-400",
};

const DAY_OPTIONS = [
  { label: "24 שעות", value: 1 },
  { label: "7 ימים", value: 7 },
  { label: "30 יום", value: 30 },
];

export const UsageDashboard: React.FC = () => {
  const [days, setDays] = useState(7);
  const { data, isLoading, isError, dataUpdatedAt } = useQuery({
    queryKey: ["usage-summary", days],
    queryFn: () => fetchUsage(days),
    refetchInterval: 30000,
  });

  const { data: unit } = useQuery({
    queryKey: ["usage-unit-costs", days],
    queryFn: () => fetchUnitCosts(days),
    refetchInterval: 30000,
  });

  const maxStageCost = Math.max(1, ...(data?.by_stage || []).map((s) => s.cost_usd));

  return (
    <div className="p-6 max-w-5xl mx-auto" dir="rtl">
      <div className="flex items-center justify-between mb-2">
        <h1 className="text-2xl font-bold text-slate-800">💰 צריכת Anthropic — לפי שלב</h1>
        <span className="text-xs text-slate-400">
          {dataUpdatedAt ? `עודכן ${new Date(dataUpdatedAt).toLocaleTimeString("he-IL")}` : ""}
        </span>
      </div>
      <p className="text-sm text-slate-500 mb-4">
        כל קריאה ל-Claude נרשמת לפי השלב בפייפליין. כך רואים בדיוק לאן הולכים הקרדיטים. העלות היא הערכה
        לפי מחירון פומבי (להשוואה יחסית, לא לחשבונאות).
      </p>

      {/* Window selector */}
      <div className="flex gap-2 mb-6">
        {DAY_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => setDays(opt.value)}
            className={`px-4 py-2 rounded-lg text-sm border transition ${
              days === opt.value
                ? "bg-slate-800 text-white border-slate-800"
                : "bg-white text-slate-600 border-slate-300 hover:bg-slate-50"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* ── Headline: average cost per unit (dynamic, all components) ── */}
      {unit && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
          <div className="bg-gradient-to-br from-emerald-600 to-emerald-700 text-white rounded-xl shadow-md p-5">
            <div className="text-sm opacity-90 mb-1">💵 עלות ממוצעת לקורות חיים אחד</div>
            <div className="text-4xl font-bold">{fmtUsd4(unit.cost_per_cv_usd)}</div>
            <div className="text-xs opacity-80 mt-2">
              כולל ניתוח Claude + חילוץ ConvertAPI · {fmtNum(unit.counts.cv_parses)} CVs
            </div>
          </div>
          <div className="bg-gradient-to-br from-amber-600 to-amber-700 text-white rounded-xl shadow-md p-5">
            <div className="text-sm opacity-90 mb-1">🎯 עלות ממוצעת להתאמה אחת</div>
            <div className="text-4xl font-bold">{fmtUsd4(unit.cost_per_match_usd)}</div>
            <div className="text-xs opacity-80 mt-2">
              ניתוח Claude להתאמה · {fmtNum(unit.counts.match_evaluations)} הערכות
            </div>
          </div>
        </div>
      )}

      {/* Cost breakdown by component (CV parse / ConvertAPI / matching / other) */}
      {unit && (
        <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-4 mb-6">
          <div className="text-sm font-semibold text-slate-700 mb-3">פילוח עלות לפי רכיב ({String(unit.days)})</div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
            {[
              { label: "ניתוח CV (Claude)", v: unit.components.cv_parse_usd },
              { label: "ConvertAPI (חילוץ)", v: unit.components.convertapi_usd },
              { label: "התאמות (Claude)", v: unit.components.agent_match_usd },
              { label: "אחר", v: unit.components.other_usd },
            ].map((c) => (
              <div key={c.label} className="bg-slate-50 rounded-lg p-3">
                <div className="text-lg font-bold text-slate-800">{fmtUsd(c.v)}</div>
                <div className="text-xs text-slate-500 mt-1">{c.label}</div>
              </div>
            ))}
          </div>
          <div className="text-xs text-slate-400 mt-3 text-center">
            סה״כ: <span className="font-semibold">{fmtUsd(unit.total_cost_usd)}</span>
          </div>
        </div>
      )}

      {isLoading && <div className="text-slate-500">טוען נתוני צריכה...</div>}
      {isError && (
        <div className="bg-red-50 border border-red-300 text-red-800 rounded-lg p-4">
          לא ניתן לטעון את נתוני הצריכה. ודא שה-backend פעיל.
        </div>
      )}

      {data && (
        <>
          {data.note && (
            <div className="bg-amber-50 border border-amber-300 text-amber-900 rounded-lg p-4 mb-6 text-sm">
              {data.note}
            </div>
          )}

          {/* Totals cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
            <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-4">
              <div className="text-xs text-slate-500 mb-1">עלות מוערכת</div>
              <div className="text-3xl font-bold text-slate-800">{fmtUsd(data.totals.cost_usd)}</div>
            </div>
            <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-4">
              <div className="text-xs text-slate-500 mb-1">סה״כ טוקנים</div>
              <div className="text-3xl font-bold text-slate-800">{fmtTokens(data.totals.total_tokens)}</div>
              <div className="text-xs text-slate-400 mt-1">
                {fmtTokens(data.totals.input_tokens)} קלט · {fmtTokens(data.totals.output_tokens)} פלט
              </div>
            </div>
            <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-4">
              <div className="text-xs text-slate-500 mb-1">קריאות API</div>
              <div className="text-3xl font-bold text-slate-800">{fmtNum(data.totals.calls)}</div>
            </div>
          </div>

          {/* By stage */}
          <h2 className="text-lg font-semibold text-slate-700 mb-3">פילוח לפי שלב</h2>
          {data.by_stage.length === 0 ? (
            <div className="text-slate-400 text-sm mb-6 bg-white border border-slate-200 rounded-lg p-6 text-center">
              אין עדיין נתוני צריכה בחלון הזמן הזה. הנתונים יצטברו ככל שהפייפליין רץ.
            </div>
          ) : (
            <div className="bg-white rounded-lg border border-slate-200 shadow-sm mb-6 divide-y divide-slate-100">
              {data.by_stage.map((s) => (
                <div key={s.stage} className="p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="font-medium text-slate-800">{s.label}</div>
                    <div className="text-sm font-semibold text-slate-700">{fmtUsd(s.cost_usd)}</div>
                  </div>
                  <div className="h-2 bg-slate-100 rounded-full overflow-hidden mb-2">
                    <div
                      className={`h-full rounded-full ${STAGE_COLORS[s.stage] || "bg-slate-400"}`}
                      style={{ width: `${(s.cost_usd / maxStageCost) * 100}%` }}
                    />
                  </div>
                  <div className="text-xs text-slate-400">
                    {fmtNum(s.calls)} קריאות · {fmtTokens(s.total_tokens)} טוקנים
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* By model */}
          {data.by_model.length > 0 && (
            <>
              <h2 className="text-lg font-semibold text-slate-700 mb-3">פילוח לפי מודל</h2>
              <div className="overflow-x-auto bg-white rounded-lg border border-slate-200 shadow-sm mb-6">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-slate-600">
                    <tr>
                      <th className="text-right px-4 py-3 font-medium">מודל</th>
                      <th className="text-right px-4 py-3 font-medium">קריאות</th>
                      <th className="text-right px-4 py-3 font-medium">טוקנים</th>
                      <th className="text-right px-4 py-3 font-medium">עלות</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_model.map((m) => (
                      <tr key={m.model} className="border-t border-slate-100 hover:bg-slate-50">
                        <td className="px-4 py-3 font-mono text-xs text-slate-700">{m.model}</td>
                        <td className="px-4 py-3 text-slate-600">{fmtNum(m.calls)}</td>
                        <td className="px-4 py-3 text-slate-600">{fmtTokens(m.total_tokens)}</td>
                        <td className="px-4 py-3 font-semibold text-slate-700">{fmtUsd(m.cost_usd)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {data.truncated && (
            <div className="text-xs text-amber-600 mb-4">
              ⚠️ הוצג מדגם חלקי (נחתך ב-{fmtNum(100000)} רשומות). הקטן את חלון הזמן לדיוק מלא.
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default UsageDashboard;
