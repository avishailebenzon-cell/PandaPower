/**
 * Agent test-conversation screen (Tal / Elad).
 *
 * The operator enters a test phone number that simulates a candidate (Tal) or a
 * client (Elad), plus the match details. On submit we create a self-contained
 * TEST match row that lands in the agent's normal queue. From there the
 * operator clicks Activate exactly like the real flow — the agent then reaches
 * out over WhatsApp to the test number, and the whole conversation is recorded
 * identically to a real one.
 */

import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FlaskConical, ArrowRight, CheckCircle2, Loader2, ListChecks, Pencil } from "lucide-react";
import {
  createTestMatch,
  listApprovedMatches,
  type CreateTestMatchResult,
  type ApprovedMatchItem,
} from "@/api/agentTest";

export interface AgentTestPanelProps {
  recruiter: "tal" | "elad";
  agentName: string; // "טל" / "אלעד"
  /** the simulated counterpart noun: "מועמד" (Tal) / "לקוח" (Elad) */
  counterpart: string;
  backTo: string;
  /** Elad: allow seeding the test from a real Carmit-approved match. */
  allowExistingMatch?: boolean;
}

export const AgentTestPanel: React.FC<AgentTestPanelProps> = ({
  recruiter,
  agentName,
  counterpart,
  backTo,
  allowExistingMatch = false,
}) => {
  const navigate = useNavigate();
  const [phone, setPhone] = useState("");
  const [contactName, setContactName] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [orgName, setOrgName] = useState("");
  const [location, setLocation] = useState("");
  const [clearance, setClearance] = useState("");
  const [candidateClearance, setCandidateClearance] = useState("");
  const [description, setDescription] = useState("");
  const [qualifications, setQualifications] = useState("");
  const [reasoning, setReasoning] = useState("");
  const [score, setScore] = useState(90);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CreateTestMatchResult | null>(null);

  // "existing" = seed from a real Carmit-approved match (Elad bypass-Tal flow).
  const [mode, setMode] = useState<"manual" | "existing">("manual");
  const [approved, setApproved] = useState<ApprovedMatchItem[]>([]);
  const [loadingApproved, setLoadingApproved] = useState(false);
  const [selectedMatchId, setSelectedMatchId] = useState<string>("");
  const [candidateName, setCandidateName] = useState("");

  useEffect(() => {
    if (mode !== "existing" || approved.length || loadingApproved) return;
    setLoadingApproved(true);
    listApprovedMatches(50)
      .then(setApproved)
      .catch((e) => setError(e?.message || "שליפת ההתאמות נכשלה"))
      .finally(() => setLoadingApproved(false));
  }, [mode]); // eslint-disable-line react-hooks/exhaustive-deps

  const applyApprovedMatch = (m: ApprovedMatchItem) => {
    setSelectedMatchId(m.match_id);
    setCandidateName(m.candidate_name);
    setJobTitle(m.job_title);
    setOrgName(m.organization_name || "");
    setLocation(m.job_location || "");
    setClearance(m.job_security_clearance || "");
    setCandidateClearance(m.candidate_clearance || "");
    setDescription(m.job_description || "");
    setQualifications(m.job_qualifications || "");
    setReasoning(m.match_reasoning || "");
    setScore(m.match_score || 90);
  };

  const isExisting = mode === "existing";
  const canSubmit =
    phone.trim() &&
    contactName.trim() &&
    jobTitle.trim() &&
    (!isExisting || selectedMatchId) &&
    !submitting;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await createTestMatch({
        recruiter,
        phone: phone.trim(),
        contact_name: contactName.trim(),
        job_title: jobTitle.trim(),
        candidate_name: candidateName.trim() || undefined,
        organization_name: orgName.trim() || undefined,
        job_location: location.trim() || undefined,
        job_security_clearance: clearance.trim() || undefined,
        candidate_clearance: candidateClearance.trim() || undefined,
        job_description: description.trim() || undefined,
        job_qualifications: qualifications.trim() || undefined,
        match_score: score,
        match_reasoning: reasoning.trim() || undefined,
      });
      setResult(res);
    } catch (e: any) {
      setError(e?.message || "יצירת שורת הבדיקה נכשלה");
    } finally {
      setSubmitting(false);
    }
  };

  const field = (
    label: string,
    value: string,
    onChange: (v: string) => void,
    opts: { required?: boolean; placeholder?: string; textarea?: boolean } = {}
  ) => (
    <label className="block">
      <span className="text-sm text-gray-300">
        {label} {opts.required && <span className="text-red-400">*</span>}
      </span>
      {opts.textarea ? (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={opts.placeholder}
          rows={3}
          className="mt-1 w-full bg-gray-800 text-white rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-teal-600"
        />
      ) : (
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={opts.placeholder}
          className="mt-1 w-full bg-gray-800 text-white rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-teal-600"
        />
      )}
    </label>
  );

  return (
    <div className="p-6 space-y-4" dir="rtl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white flex items-center gap-2">
            <FlaskConical className="w-7 h-7 text-amber-400" /> שיחת בדיקה — {agentName}
          </h1>
          <p className="text-gray-400 mt-1">
            יצירת שורת התאמה לבדיקה עם מספר טלפון שמדמה {counterpart}. לאחר היצירה
            השורה תופיע בתור הרגיל של {agentName}, ומשם תפעיל אקטיבציה כרגיל —{" "}
            {agentName} תפנה למספר הבדיקה והשיחה תתועד בדיוק כמו שיחה אמיתית.
          </p>
        </div>
        <button
          onClick={() => navigate(backTo)}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-700 text-white hover:bg-gray-600 transition"
        >
          חזרה <ArrowRight className="w-4 h-4" />
        </button>
      </div>

      {result ? (
        <div className="max-w-2xl rounded-lg border border-green-700 bg-green-900/30 p-5 space-y-3">
          <div className="flex items-center gap-2 text-green-300 font-semibold">
            <CheckCircle2 className="w-5 h-5" /> שורת הבדיקה נוצרה בתור של {agentName}
          </div>
          <p className="text-sm text-gray-300">
            ההתאמה ({contactName} — {jobTitle}) נוספה כשורה אמיתית במצב{" "}
            <code className="text-amber-300">{result.state}</code>. עבור לתור,
            לחץ על השורה והפעל אקטיבציה — {agentName} תשלח הודעת פתיחה למספר{" "}
            {phone}.
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => navigate(result.queue_path)}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition"
            >
              עבור לתור של {agentName} <ArrowRight className="w-4 h-4" />
            </button>
            <button
              onClick={() => {
                setResult(null);
              }}
              className="px-4 py-2 rounded-lg bg-gray-700 text-white hover:bg-gray-600 transition"
            >
              צור שורת בדיקה נוספת
            </button>
          </div>
        </div>
      ) : (
        <div className="max-w-2xl rounded-lg border border-gray-700 bg-gray-900/50 p-5 space-y-4">
          {error && (
            <div className="rounded-lg bg-red-900/40 border border-red-800 text-red-200 text-sm px-3 py-2">
              {error}
            </div>
          )}

          {allowExistingMatch && (
            <div className="flex gap-2 rounded-lg bg-gray-800/60 p-1 w-fit">
              <button
                onClick={() => {
                  setMode("existing");
                  setError(null);
                }}
                className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition ${
                  isExisting ? "bg-teal-600 text-white" : "text-gray-300 hover:bg-gray-700"
                }`}
              >
                <ListChecks className="w-4 h-4" /> בחר התאמה שכרמית אישרה
              </button>
              <button
                onClick={() => {
                  setMode("manual");
                  setSelectedMatchId("");
                  setError(null);
                }}
                className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition ${
                  !isExisting ? "bg-teal-600 text-white" : "text-gray-300 hover:bg-gray-700"
                }`}
              >
                <Pencil className="w-4 h-4" /> הזנה ידנית
              </button>
            </div>
          )}

          {isExisting && (
            <div className="space-y-3">
              <label className="block">
                <span className="text-sm text-gray-300">
                  התאמה קיימת (מתוך התאמות שכרמית אישרה) <span className="text-red-400">*</span>
                </span>
                <select
                  value={selectedMatchId}
                  onChange={(e) => {
                    const m = approved.find((x) => x.match_id === e.target.value);
                    if (m) applyApprovedMatch(m);
                    else setSelectedMatchId("");
                  }}
                  className="mt-1 w-full bg-gray-800 text-white rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-teal-600"
                >
                  <option value="">
                    {loadingApproved
                      ? "טוען התאמות…"
                      : approved.length
                      ? "— בחר התאמה —"
                      : "אין התאמות מאושרות במאגר"}
                  </option>
                  {approved.map((m) => (
                    <option key={m.match_id} value={m.match_id}>
                      {m.candidate_name} ← {m.job_title}
                      {m.organization_name ? ` (${m.organization_name})` : ""} · {m.match_score}%
                    </option>
                  ))}
                </select>
              </label>

              {selectedMatchId && (
                <div className="rounded-lg border border-gray-700 bg-gray-800/40 p-4 text-sm text-gray-200 space-y-1">
                  <div>👤 מועמד: <b>{candidateName}</b>{candidateClearance ? ` · סיווג ${candidateClearance}` : ""}</div>
                  <div>💼 משרה: <b>{jobTitle}</b>{orgName ? ` · ${orgName}` : ""}</div>
                  {location && <div>📍 מיקום: {location}</div>}
                  {clearance && <div>🔒 סיווג נדרש: {clearance}</div>}
                  <div>📊 ציון התאמה: {score}%</div>
                  {reasoning && <div className="text-gray-400 pt-1">📝 {reasoning}</div>}
                  <p className="text-xs text-amber-300/80 pt-2">
                    עוקפים את שלב טל ומניחים שההתאמה כבר אושרה — אלעד יציג את המועמד ללקוח הבדיקה.
                  </p>
                </div>
              )}
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {field(`טלפון ${counterpart} לבדיקה`, phone, setPhone, {
              required: true,
              placeholder: "+972…",
            })}
            {field(`שם ${counterpart}`, contactName, setContactName, {
              required: true,
              placeholder: counterpart === "לקוח" ? "איש קשר אצל הלקוח" : "שם המועמד",
            })}
            {!isExisting && field("כותרת המשרה", jobTitle, setJobTitle, { required: true })}
            {!isExisting && field("שם הארגון/לקוח", orgName, setOrgName)}
            {!isExisting && field("מיקום", location, setLocation)}
            {!isExisting && field("סיווג ביטחוני נדרש", clearance, setClearance)}
          </div>
          {!isExisting && field("תיאור המשרה", description, setDescription, { textarea: true })}
          {!isExisting && field("דרישות התפקיד", qualifications, setQualifications, { textarea: true })}
          {!isExisting && field("נימוק ההתאמה (אופציונלי)", reasoning, setReasoning, { textarea: true })}
          {!isExisting && (
            <label className="block">
              <span className="text-sm text-gray-300">ציון התאמה: {score}%</span>
              <input
                type="range"
                min={0}
                max={100}
                value={score}
                onChange={(e) => setScore(Number(e.target.value))}
                className="mt-1 w-full"
              />
            </label>
          )}

          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-amber-600 text-white hover:bg-amber-500 transition disabled:opacity-50"
          >
            {submitting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <FlaskConical className="w-4 h-4" />
            )}
            צור שורת בדיקה
          </button>
        </div>
      )}
    </div>
  );
};

export default AgentTestPanel;
