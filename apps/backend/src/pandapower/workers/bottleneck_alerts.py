"""
Bottleneck Detection & Alert Service

Periodically checks the recruitment pipeline for bottlenecks and sends alerts
when matches are stuck or flow is imbalanced.

Bottleneck Rules:
1. Tal Screening: sent_to_tal > tal_accepted * 2 (too many waiting)
2. Elad Placement: tal_accepted > sent_to_elad * 2 (ready candidates not being placed)
3. Stagnation: Any match in same stage for >7 days without progress
4. Rejection Rate: rejected_* > 30% of total completed
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class BottleneckAlert:
    """Represents a detected bottleneck."""

    def __init__(
        self,
        alert_type: str,
        level: AlertLevel,
        title: str,
        description: str,
        metrics: dict[str, Any],
        recommendation: str,
    ):
        self.alert_type = alert_type  # "tal_screening", "elad_placement", "stagnation", "rejection_rate"
        self.level = level
        self.title = title
        self.description = description
        self.metrics = metrics
        self.recommendation = recommendation
        self.detected_at = datetime.utcnow()

    def to_dict(self) -> dict:
        return {
            "alert_type": self.alert_type,
            "level": self.level.value,
            "title": self.title,
            "description": self.description,
            "metrics": self.metrics,
            "recommendation": self.recommendation,
            "detected_at": self.detected_at.isoformat(),
        }


class BottleneckDetector:
    """Analyzes pipeline flow and detects bottlenecks."""

    def __init__(self, supabase_client: Any):
        self.supabase = supabase_client

    async def detect_all(self) -> list[BottleneckAlert]:
        """Run all bottleneck detection rules."""
        alerts = []

        try:
            # Fetch all matches
            matches_response = await self.supabase.table("matches").select(
                "id, current_state, created_at, updated_at"
            ).execute()

            matches = matches_response.data or []

            # Count by stage
            stage_counts = self._count_by_stage(matches)

            # Check all rules
            alerts.extend(self._check_tal_screening_bottleneck(stage_counts))
            alerts.extend(self._check_elad_placement_bottleneck(stage_counts))
            alerts.extend(self._check_stagnation(matches))
            alerts.extend(self._check_rejection_rate(stage_counts))

            logger.info(f"Bottleneck detection: found {len(alerts)} alerts")

        except Exception as e:
            logger.error(f"Error detecting bottlenecks: {e}", exc_info=True)

        return alerts

    def _count_by_stage(self, matches: list[dict]) -> dict[str, int]:
        """Count matches by stage."""
        counts = {
            "found": 0,
            "carmit_approved": 0,
            "sent_to_tal": 0,
            "tal_conversation": 0,
            "tal_accepted": 0,
            "sent_to_elad": 0,
            "hired": 0,
            "rejected_tal": 0,
            "rejected_elad": 0,
        }

        for match in matches:
            state = match.get("current_state", "found")
            if state in counts:
                counts[state] += 1

        return counts

    def _check_tal_screening_bottleneck(
        self, stage_counts: dict[str, int]
    ) -> list[BottleneckAlert]:
        """Check if Tal is overloaded with candidates waiting for screening."""
        alerts = []

        sent_to_tal = stage_counts["sent_to_tal"]
        tal_accepted = stage_counts["tal_accepted"]

        # Rule: sent_to_tal > tal_accepted * 2
        if tal_accepted > 0 and sent_to_tal > tal_accepted * 2:
            ratio = sent_to_tal / tal_accepted
            alerts.append(
                BottleneckAlert(
                    alert_type="tal_screening",
                    level=AlertLevel.WARNING if ratio < 4 else AlertLevel.CRITICAL,
                    title=f"🚨 Tal Bottleneck: {sent_to_tal} waiting ({ratio:.1f}x ratio)",
                    description=f"Too many candidates waiting for Tal's screening. "
                    f"{sent_to_tal} in 'sent_to_tal', only {tal_accepted} approved.",
                    metrics={
                        "sent_to_tal": sent_to_tal,
                        "tal_accepted": tal_accepted,
                        "ratio": ratio,
                    },
                    recommendation=f"Tal needs to accelerate screening. "
                    f"Consider assigning additional resources or prioritizing high-score candidates.",
                )
            )
        elif tal_accepted == 0 and sent_to_tal > 3:
            alerts.append(
                BottleneckAlert(
                    alert_type="tal_screening",
                    level=AlertLevel.WARNING,
                    title=f"⚠️ Tal Screening Stalled: {sent_to_tal} candidates, 0 approved",
                    description="Candidates are waiting for Tal's review but none have been approved yet.",
                    metrics={"sent_to_tal": sent_to_tal, "tal_accepted": 0},
                    recommendation="Follow up with Tal to check on screening progress.",
                )
            )

        return alerts

    def _check_elad_placement_bottleneck(
        self, stage_counts: dict[str, int]
    ) -> list[BottleneckAlert]:
        """Check if Elad is slow in placing candidates."""
        alerts = []

        tal_accepted = stage_counts["tal_accepted"]
        sent_to_elad = stage_counts["sent_to_elad"]

        # Rule: tal_accepted > sent_to_elad * 2
        if sent_to_elad > 0 and tal_accepted > sent_to_elad * 2:
            ratio = tal_accepted / sent_to_elad
            alerts.append(
                BottleneckAlert(
                    alert_type="elad_placement",
                    level=AlertLevel.WARNING if ratio < 4 else AlertLevel.CRITICAL,
                    title=f"🚨 Elad Placement Bottleneck: {tal_accepted} ready ({ratio:.1f}x ratio)",
                    description=f"Candidates are approved but not being sent to clients. "
                    f"{tal_accepted} ready for placement, only {sent_to_elad} with Elad.",
                    metrics={
                        "tal_accepted": tal_accepted,
                        "sent_to_elad": sent_to_elad,
                        "ratio": ratio,
                    },
                    recommendation=f"Elad needs to increase placement pace. "
                    f"Check if client restrictions or candidate fit issues are causing delays.",
                )
            )
        elif sent_to_elad == 0 and tal_accepted > 2:
            alerts.append(
                BottleneckAlert(
                    alert_type="elad_placement",
                    level=AlertLevel.WARNING,
                    title=f"⚠️ No Placements: {tal_accepted} candidates ready, 0 with Elad",
                    description="Candidates are approved by Tal but haven't been sent to clients.",
                    metrics={"tal_accepted": tal_accepted, "sent_to_elad": 0},
                    recommendation="Initiate placements with Elad immediately.",
                )
            )

        return alerts

    def _check_stagnation(self, matches: list[dict]) -> list[BottleneckAlert]:
        """Check for matches stuck in same stage for too long."""
        alerts = []
        stagnant_matches = []
        stagnation_threshold = timedelta(days=7)
        now = datetime.utcnow()

        for match in matches:
            updated = datetime.fromisoformat(match["updated_at"].replace("Z", "+00:00"))
            time_in_stage = now - updated

            # Skip terminal states
            state = match.get("current_state", "found")
            if state not in ["hired", "rejected_tal", "rejected_elad"]:
                if time_in_stage > stagnation_threshold:
                    stagnant_matches.append({
                        "id": match["id"],
                        "state": state,
                        "days_in_stage": time_in_stage.days,
                    })

        if stagnant_matches:
            days_list = [m["days_in_stage"] for m in stagnant_matches]
            max_days = max(days_list)
            alerts.append(
                BottleneckAlert(
                    alert_type="stagnation",
                    level=AlertLevel.WARNING,
                    title=f"⏰ {len(stagnant_matches)} matches stuck (max {max_days}d)",
                    description=f"{len(stagnant_matches)} matches haven't progressed in >{stagnation_threshold.days} days.",
                    metrics={
                        "stagnant_count": len(stagnant_matches),
                        "max_days_stuck": max_days,
                        "matches": stagnant_matches,
                    },
                    recommendation="Review stagnant matches for issues: candidate unavailable? "
                    "Client changed mind? Mismatch in expectations?",
                )
            )

        return alerts

    def _check_rejection_rate(self, stage_counts: dict[str, int]) -> list[BottleneckAlert]:
        """Check if rejection rate is too high."""
        alerts = []

        rejected_tal = stage_counts["rejected_tal"]
        rejected_elad = stage_counts["rejected_elad"]
        hired = stage_counts["hired"]

        total_completed = rejected_tal + rejected_elad + hired

        if total_completed > 0:
            rejection_rate = (rejected_tal + rejected_elad) / total_completed

            if rejection_rate > 0.5:  # >50% rejection
                alerts.append(
                    BottleneckAlert(
                        alert_type="rejection_rate",
                        level=AlertLevel.CRITICAL,
                        title=f"🔴 High Rejection Rate: {rejection_rate * 100:.0f}%",
                        description=f"More than half of completed matches were rejected. "
                        f"Hired: {hired}, Rejected: {rejected_tal + rejected_elad}.",
                        metrics={
                            "hired": hired,
                            "rejected_tal": rejected_tal,
                            "rejected_elad": rejected_elad,
                            "rejection_rate": rejection_rate,
                        },
                        recommendation="Review matching criteria: are candidates mismatched? "
                        "Are clients being too selective? Consider adjusting scoring algorithm.",
                    )
                )
            elif rejection_rate > 0.35:  # >35% rejection
                alerts.append(
                    BottleneckAlert(
                        alert_type="rejection_rate",
                        level=AlertLevel.WARNING,
                        title=f"⚠️ Elevated Rejection Rate: {rejection_rate * 100:.0f}%",
                        description=f"Rejection rate is above healthy threshold (35%). "
                        f"Hired: {hired}, Rejected: {rejected_tal + rejected_elad}.",
                        metrics={
                            "hired": hired,
                            "rejected_tal": rejected_tal,
                            "rejected_elad": rejected_elad,
                            "rejection_rate": rejection_rate,
                        },
                        recommendation="Monitor rejection patterns. Check if specific candidate types "
                        "or job types have higher rejection rates.",
                    )
                )

        return alerts


async def check_and_alert_bottlenecks(supabase_client: Any, alert_service: Any) -> dict:
    """
    Main entry point: detect bottlenecks and send alerts.

    Args:
        supabase_client: Supabase DB client
        alert_service: Alert service (e.g., ResendAlertService)

    Returns:
        {
            "status": "ok" | "has_alerts",
            "alerts_detected": int,
            "alerts": [BottleneckAlert.to_dict()],
            "alerts_sent": int,
        }
    """
    try:
        detector = BottleneckDetector(supabase_client)
        alerts = await detector.detect_all()

        result = {
            "status": "has_alerts" if alerts else "ok",
            "alerts_detected": len(alerts),
            "alerts": [a.to_dict() for a in alerts],
            "alerts_sent": 0,
        }

        # Send each alert via the alert service
        if alert_service and alerts:
            for alert in alerts:
                try:
                    await alert_service.send_bottleneck_alert(alert)
                    result["alerts_sent"] += 1
                except Exception as e:
                    logger.error(f"Failed to send alert: {e}")

        logger.info(f"Bottleneck check complete: {result['alerts_detected']} alerts, {result['alerts_sent']} sent")
        return result

    except Exception as e:
        logger.error(f"Error in bottleneck alert check: {e}", exc_info=True)
        return {"status": "error", "error": str(e), "alerts_detected": 0, "alerts_sent": 0}
