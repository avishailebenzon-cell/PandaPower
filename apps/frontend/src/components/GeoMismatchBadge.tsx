/**
 * GeoMismatchBadge — a bold, impossible-to-miss red flag shown on any match
 * where the candidate is an excellent professional fit but lives too far from
 * the job to commute ("אין התאמה גיאוגרפית").
 *
 * The match is intentionally KEPT (some candidates relocate for the right
 * role) — this badge just makes the geographic gap obvious so Carmit/Tal can
 * decide whether to promote it to a Tal conversation.
 *
 * Rendered nowhere when there is no mismatch.
 */

interface Props {
  /** True when the matching agent flagged a geographic mismatch. */
  mismatch?: boolean;
  /** Optional Hebrew explanation (cities + rough distance) shown on hover. */
  reason?: string;
  /** "sm" for table rows (default), "lg" for the detail modal. */
  size?: "sm" | "lg";
}

export function GeoMismatchBadge({ mismatch, reason, size = "sm" }: Props) {
  if (!mismatch) return null;

  const sizeCls = size === "lg" ? "px-3 py-2 text-sm" : "px-2 py-1 text-xs";

  return (
    <span
      title={reason || "המועמד אינו נמצא במיקום גיאוגרפי מתאים למשרה"}
      className={`inline-flex items-center gap-1 rounded font-bold text-white bg-red-600 ring-1 ring-red-300/70 whitespace-nowrap animate-pulse ${sizeCls}`}
    >
      <span>📍</span>
      <span>אין התאמה גיאוגרפית</span>
    </span>
  );
}

export default GeoMismatchBadge;
