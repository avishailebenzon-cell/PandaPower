"""Tool handlers for Pandi conversation engine tool calls."""

import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pandapower.core.supabase import get_supabase_client

import structlog as _structlog
logger = _structlog.get_logger(__name__)


async def handle_update_job_context(
    conversation_id: UUID,
    pandi_client_id: UUID,
    **context_fields: Any
) -> dict[str, Any]:
    """Handle update_job_context tool call.

    Args:
        conversation_id: UUID of conversation
        pandi_client_id: UUID of Pandi client
        **context_fields: Job context fields to update

    Returns:
        Result of update operation
    """
    try:
        from .job_context_builder import JobContextBuilder

        builder = JobContextBuilder()

        # Prepare context dict (filter None values)
        new_context = {k: v for k, v in context_fields.items() if v is not None}

        if not new_context:
            return {"status": "success", "message": "No new context to update"}

        # Update conversation job context
        await builder.update_conversation_job_context(
            conversation_id=conversation_id,
            new_context=new_context,
        )

        logger.info(
            "job_context_updated_via_tool",
            conversation_id=str(conversation_id),
            fields=list(new_context.keys()),
        )

        return {
            "status": "success",
            "message": "עדכנתי את הדרישות שלך לתפקיד",
            "updated_fields": list(new_context.keys()),
        }

    except Exception as e:
        logger.error(f"update_job_context failed: {e}", exc_info=True)
        return {
            "status": "error",
            "message": "סליחה, קצת בעיה בעדכון הדרישות",
            "error": str(e),
        }


async def handle_search_candidates(
    conversation_id: UUID,
    pandi_client_id: UUID,
    context_summary: str,
    limit: int = 5,
) -> dict[str, Any]:
    """Handle search_candidates tool call.

    Args:
        conversation_id: UUID of conversation
        pandi_client_id: UUID of Pandi client
        context_summary: Summary of what we're looking for
        limit: Max candidates to return

    Returns:
        Search results with candidates
    """
    try:
        from .candidate_matching import search_candidates_for_context

        # Load full job context from conversation
        supabase = await get_supabase_client()
        _conv_res = await supabase.table("pandi_conversations").select(
            "job_context"
        ).eq("id", str(conversation_id)).limit(1).execute()
        conversation = _conv_res.data[0] if _conv_res.data else None

        job_context = conversation.get("job_context", {}) if conversation else {}

        # Call real search implementation (Session 30)
        result = await search_candidates_for_context(job_context, limit)

        if result.get("status") == "success":
            candidates = result.get("candidates", [])
            logger.info(
                "candidates_searched",
                conversation_id=str(conversation_id),
                count=len(candidates),
            )

            # Session 32: Create referral records for each candidate presented
            from .referral_manager import ReferralManager

            manager = ReferralManager()
            formatted_candidates = []

            for candidate in candidates:
                candidate_number = candidate.get("candidate_number")
                candidate_id = candidate.get("candidate_id")

                if candidate_id:
                    # Create referral record (if not already in this conversation)
                    referral = await manager.create_referral(
                        candidate_id=UUID(candidate_id),
                        candidate_number=candidate_number,
                        pandi_client_id=pandi_client_id,
                        conversation_id=conversation_id,
                        job_context=job_context,
                        presented_payload={
                            "number": candidate_number,
                            "score": candidate.get("match_score"),
                            "years_experience": candidate.get("years_experience"),
                            "skills": candidate.get("top_skills", []),
                            "summary": candidate.get("summary"),
                        },
                        llm_match_reasoning=candidate.get("reasoning"),
                    )

                    if referral.get("status") != "error":
                        logger.info(
                            "referral_created_for_presentation",
                            candidate_number=candidate_number,
                            referral_id=referral.get("referral_id"),
                        )

                # Format for LLM response — anonymized: iron number + capabilities,
                # NEVER name/phone/email/company.
                formatted_candidates.append({
                    "number": candidate_number,
                    "score": candidate.get("match_score"),
                    "years_experience": candidate.get("years_experience"),
                    "domain": candidate.get("domain"),
                    "security_clearance": candidate.get("security_clearance"),
                    "location": candidate.get("location"),
                    "skills": candidate.get("top_skills", []),
                    "summary": candidate.get("summary"),
                    "reasoning": candidate.get("reasoning"),
                })

            return {
                "status": "success",
                "candidates": formatted_candidates,
                "total": len(candidates),
                "message": f"מצאתי {len(candidates)} מועמדים שנראים מתאימים",
            }
        else:
            return {
                "status": "no_candidates",
                "message": "לא מצאתי מועמדים התואמים כרגע. בואו נזומת יותר על הדרישות שלך.",
            }

    except Exception as e:
        logger.error(f"search_candidates failed: {e}", exc_info=True)
        return {
            "status": "error",
            "message": "סליחה, קצת בעיה בחיפוש המועמדים",
            "error": str(e),
        }


async def handle_mark_client_interested(
    conversation_id: UUID,
    pandi_client_id: UUID,
    candidate_number: str,
    interest_reason: Optional[str] = None,
) -> dict[str, Any]:
    """Handle mark_client_interested tool call.

    Session 32: Uses real referral manager instead of mock.

    Args:
        conversation_id: UUID of conversation
        pandi_client_id: UUID of Pandi client
        candidate_number: Candidate number (e.g., C000123)
        interest_reason: Optional reason for interest

    Returns:
        Result of marking interest
    """
    try:
        from .referral_manager import ReferralManager

        # Get candidate ID from candidate_number
        supabase = await get_supabase_client()
        _cand_res = await supabase.table("candidates").select(
            "id"
        ).eq("candidate_number", candidate_number).limit(1).execute()
        candidate = _cand_res.data[0] if _cand_res.data else None

        if not candidate:
            logger.warning(
                "candidate_not_found_by_number",
                candidate_number=candidate_number,
            )
            return {
                "status": "error",
                "message": f"סליחה, לא מצאתי את המועמד {candidate_number}",
            }

        # Use real referral manager
        manager = ReferralManager()
        result = await manager.mark_client_interested(
            candidate_number=candidate_number,
            candidate_id=UUID(candidate["id"]),
            pandi_client_id=pandi_client_id,
            conversation_id=conversation_id,
            interest_reason=interest_reason,
        )

        if result.get("status") == "success":
            logger.info(
                "client_interested_marked",
                conversation_id=str(conversation_id),
                candidate_number=candidate_number,
                pandi_client_id=str(pandi_client_id),
                referral_id=result.get("referral_id"),
            )

            # Get referral_number from the referral that was just created/updated
            referral_id = result.get("referral_id")
            referral_number = "REF-2026-?"
            if referral_id:
                _ref_res = await supabase.table("candidate_referrals").select(
                    "referral_number, candidate_number"
                ).eq("id", str(referral_id)).limit(1).execute()
                referral_result = _ref_res.data[0] if _ref_res.data else None

                if referral_result:
                    referral_number = referral_result.get("referral_number", referral_number)

            # Send notifications (manager + client via Pandi)
            try:
                from pandapower.integrations.resend_client import ResendClient
                from pandapower.core.config import settings

                if settings.RESEND_API_KEY:
                    resend = ResendClient(api_key=settings.RESEND_API_KEY)
                    from pandapower.integrations.alert_service import get_admin_email
                    admin_email = await get_admin_email(supabase)

                    # Notify manager
                    await resend.send_email(
                        to=[admin_email],
                        from_addr=settings.RESEND_FROM_EMAIL,
                        subject=f"🎯 פנייה חדשה: {candidate_number}",
                        html=f"""
                        <p>פנייה חדשה בדבר מועמד:</p>
                        <p><strong>מספר פנייה:</strong> {referral_number}</p>
                        <p><strong>מועמד:</strong> {candidate_number}</p>
                        <p><strong>סטטוס:</strong> הלקוח בחר בעניין</p>
                        <p><strong>SLA:</strong> 48 שעות</p>
                        <p>בואו נטפל בפנייה!</p>
                        """.replace("\n", ""),
                    )
            except Exception as e:
                logger.warning(f"Failed to send manager email: {e}")

            return {
                "status": "success",
                "referral_number": referral_number,
                # NOTE: this string is internal context for the model, not shown
                # to the client verbatim. The choice is recorded; the next step is
                # to ask the client to CONFIRM sending the full Panda-Tech CV, then
                # call send_candidate_cv. Do NOT promise "a manager will call in 48h".
                "message": f"רשמתי שהלקוח בחר ב-{candidate_number} (מס' פנייה: {referral_number}). עכשיו בקשי אישור מפורש לשליחת קורות החיים המלאים, ואז קראי ל-send_candidate_cv.",
            }
        else:
            return {
                "status": "error",
                "message": result.get("message", "סליחה, קצת בעיה בתיעוד ההעניין"),
            }

    except Exception as e:
        logger.error(f"mark_client_interested failed: {e}", exc_info=True)
        return {
            "status": "error",
            "message": "סליחה, קצת בעיה בתיעוד ההעניין",
            "error": str(e),
        }


async def handle_check_referral_history(
    conversation_id: UUID,
    pandi_client_id: UUID,
    candidate_number: str,
) -> dict[str, Any]:
    """Handle check_referral_history tool call.

    Session 32: Uses real referral manager to check actual history.

    Args:
        conversation_id: UUID of conversation
        pandi_client_id: UUID of Pandi client
        candidate_number: Candidate number to check

    Returns:
        Referral history information
    """
    try:
        from .referral_manager import ReferralManager

        # Get candidate ID from candidate_number
        supabase = await get_supabase_client()
        _cand_res = await supabase.table("candidates").select(
            "id"
        ).eq("candidate_number", candidate_number).limit(1).execute()
        candidate = _cand_res.data[0] if _cand_res.data else None

        if not candidate:
            logger.warning(
                "candidate_not_found_for_history",
                candidate_number=candidate_number,
            )
            return {
                "status": "success",
                "message": f"לא מצאתי את המועמד {candidate_number} במערכת",
                "previous_offers": 0,
                "previous_decline": False,
            }

        # Use real referral manager
        manager = ReferralManager()
        history = await manager.check_referral_history(
            candidate_id=UUID(candidate["id"]),
            pandi_client_id=pandi_client_id,
        )

        if history.get("status") == "success":
            previous_offers = history.get("previous_offers", 0)
            previous_decline = history.get("previous_decline", False)
            hired = history.get("hired", False)

            message = f"עבור {candidate_number}: "
            if previous_offers == 0:
                message += "לא הצענו את המועמד הזה קודם. חדש לחלוטין! ✨"
            elif hired:
                message += f"כבר הצענו את המועמד הזה ו... הוא נשכר! 🎉"
            else:
                message += f"הצענו את המועמד הזה {previous_offers} פעם/ים "
                if previous_decline:
                    message += "אבל הוא דחה בעבר. אפשר לנסות שוב אם התנאים השתנו. 🤔"
                else:
                    message += "ויש סיכוי טוב שיהיה מעוניין! 👍"

            logger.info(
                "referral_history_checked",
                conversation_id=str(conversation_id),
                candidate_number=candidate_number,
                previous_offers=previous_offers,
            )

            return {
                "status": "success",
                "message": message,
                "previous_offers": previous_offers,
                "previous_decline": previous_decline,
                "hired": hired,
                "outcomes": history.get("outcomes", []),
            }
        else:
            return {
                "status": "error",
                "message": "סליחה, לא הצלחתי לבדוק את ההיסטוריה",
            }

    except Exception as e:
        logger.error(f"check_referral_history failed: {e}", exc_info=True)
        return {
            "status": "error",
            "message": "סליחה, קצת בעיה בבדיקת ההיסטוריה",
            "error": str(e),
        }


async def handle_request_quota_increase(
    conversation_id: UUID,
    pandi_client_id: UUID,
    additional_messages: int = 50,
    reason: Optional[str] = None,
) -> dict[str, Any]:
    """Handle request_quota_increase tool call.

    Args:
        conversation_id: UUID of conversation
        pandi_client_id: UUID of Pandi client
        additional_messages: Number of additional messages requested
        reason: Reason for the increase

    Returns:
        Result of quota increase request
    """
    try:
        from .tools import request_quota_increase_impl

        result = await request_quota_increase_impl(
            additional_messages=additional_messages,
            reason=reason,
        )

        if result.get("status") == "success":
            logger.info(
                "quota_increase_requested",
                conversation_id=str(conversation_id),
                pandi_client_id=str(pandi_client_id),
                additional_messages=additional_messages,
            )

            return {
                "status": "success",
                "message": f"בקשתך להגדלת מכסה ב-{additional_messages} הודעות נשלחה לאדמין. אנחנו נעדכן אותך כשהיא תאושר! 📈",
            }
        else:
            return {
                "status": "error",
                "message": "סליחה, קצת בעיה בשליחת הבקשה",
            }

    except Exception as e:
        logger.error(f"request_quota_increase failed: {e}", exc_info=True)
        return {
            "status": "error",
            "message": "סליחה, קצת בעיה בשליחת בקשת ההגדלה",
            "error": str(e),
        }


async def handle_transfer_to_recruitment(
    conversation_id: UUID,
    pandi_client_id: UUID,
    summary: str,
) -> dict[str, Any]:
    """Handle transfer_to_recruitment tool call.

    Args:
        conversation_id: UUID of conversation
        pandi_client_id: UUID of Pandi client
        summary: Summary of conversation to hand off

    Returns:
        Result of transfer operation
    """
    try:
        from .tools import transfer_to_recruitment_impl

        result = await transfer_to_recruitment_impl(summary)

        if result.get("status") == "success":
            # Update conversation status to transferred_to_recruitment
            supabase = await get_supabase_client()
            await supabase.table("pandi_conversations").update(
                {"status": "transferred_to_recruitment"}
            ).eq("id", str(conversation_id)).execute()

            logger.info(
                "conversation_transferred",
                conversation_id=str(conversation_id),
                pandi_client_id=str(pandi_client_id),
            )

            return {
                "status": "success",
                "message": "העברתי את הטיפול לצוות הגיוס שלנו. הם יצרו אתך קשר בקרוב! 🤝",
            }
        else:
            return {
                "status": "error",
                "message": "סליחה, קצת בעיה בהעברה לצוות",
            }

    except Exception as e:
        logger.error(f"transfer_to_recruitment failed: {e}", exc_info=True)
        return {
            "status": "error",
            "message": "סליחה, קצת בעיה בהעברה לצוות",
            "error": str(e),
        }


async def handle_identify_client(
    conversation_id: UUID,
    pandi_client_id: UUID,
    phone: str,
) -> dict[str, Any]:
    """Phase 1 (Opening): Check if client already exists in DB by phone.

    Args:
        conversation_id: UUID of conversation
        pandi_client_id: UUID of Pandi client (may be pre-created stub)
        phone: Phone number in E.164 format

    Returns:
        Status and client details if found, or 'not_found' if new client
    """
    try:
        supabase = await get_supabase_client()

        # Search contacts by phone
        _id_res = await supabase.table("contacts").select(
            "id, full_name, email, organization_id, contact_status, professional_domain"
        ).eq("phone", phone).limit(1).execute()
        result = _id_res.data[0] if _id_res.data else None

        if result:
            logger.info(
                "client_identified",
                phone=phone,
                contact_id=result["id"],
            )
            return {
                "status": "found",
                "client_exists": True,
                "contact_id": result["id"],
                "full_name": result.get("full_name"),
                "email": result.get("email"),
                "contact_status": result.get("contact_status"),
                "message": f"שלום {result.get('full_name', 'חברים')}! 👋 רוצה לומר לי בשנית מה בדעתך?",
            }
        else:
            logger.info(
                "client_not_found",
                phone=phone,
            )
            return {
                "status": "not_found",
                "client_exists": False,
                "message": "אתה לקוח חדש. בואו נתחיל - אני צריך את הפרטים שלך: שם מלא, מייל, החברה שלך ותפקיד",
            }

    except Exception as e:
        logger.error(f"identify_client failed: {e}", exc_info=True)
        return {
            "status": "error",
            "message": "סליחה, קצת בעיה בזיהוי. אנא נסה שנית",
            "error": str(e),
        }


async def handle_create_client(
    conversation_id: UUID,
    pandi_client_id: UUID,
    phone: str,
    full_name: str,
    email: str,
    company_name: str = None,
    role: str = None,
) -> dict[str, Any]:
    """Phase 1 (Opening): Create new client in DB, sync to Pipedrive, notify admin.

    Args:
        conversation_id: UUID of conversation
        pandi_client_id: UUID of Pandi client
        phone: Phone number in E.164 format
        full_name: Full name
        email: Email address
        company_name: Optional company name
        role: Optional role/title

    Returns:
        Result of client creation
    """
    try:
        supabase = await get_supabase_client()

        # Use the client's REAL phone from pandi_clients, never the phone the LLM
        # passed in — the model often invents a placeholder (e.g. +972500000000)
        # because it doesn't actually know the WhatsApp number. The stored phone
        # is the authentic sender number captured from the webhook.
        try:
            _pc = await supabase.table("pandi_clients").select(
                "phone, whatsapp_chat_id"
            ).eq("id", str(pandi_client_id)).limit(1).execute()
            real_phone = (_pc.data[0].get("phone") if _pc.data else None) or ""
            if real_phone:
                if not real_phone.startswith("+"):
                    real_phone = "+" + real_phone.lstrip("+")
                phone = real_phone
        except Exception as _e:
            logger.warning(f"could not load real phone for client {pandi_client_id}: {_e}")

        # 1. Check if contact already exists (double-check)
        _exist_res = await supabase.table("contacts").select(
            "id"
        ).eq("phone", phone).limit(1).execute()
        existing = _exist_res.data[0] if _exist_res.data else None

        if existing:
            logger.warning(
                "client_already_exists",
                phone=phone,
                contact_id=existing["id"],
            )
            return {
                "status": "already_exists",
                "message": f"הלקוח הזה כבר קיים במערכת. contact_id: {existing['id']}",
                "contact_id": existing["id"],
            }

        # 2. Create new contact in Pipedrive first
        from pandapower.integrations.pipedrive import PipedriveClient
        from pandapower.core.config import settings

        # Pipedrive person creation is BEST-EFFORT. If Pipedrive is unconfigured,
        # rate-limited (429), or otherwise failing, we must still register the
        # client locally so Pandi can keep the conversation going — the contact
        # gets synced to Pipedrive later by the regular sync. Never let a CRM
        # hiccup turn into "סליחה, בעיה בשמירת הפרטים".
        pipedrive_person_id = None
        if settings.PIPEDRIVE_API_TOKEN:
            try:
                pipedrive_client = PipedriveClient(
                    settings.PIPEDRIVE_API_TOKEN,
                    settings.PIPEDRIVE_API_DOMAIN or "https://api.pipedrive.com",
                )
                from pandapower.workers.pipedrive_sync import CONTACT_STATUS_FIELD

                CONTACT_STATUS_POTENTIAL_CLIENT = 33  # לקוח פוטנציאלי

                # company_name / role are NOT person fields in Pipedrive — they
                # go only to the admin notification below.
                pd_person = await pipedrive_client.create_person(
                    name=full_name,
                    email=email,
                    phone=phone,
                    custom_fields={
                        CONTACT_STATUS_FIELD: CONTACT_STATUS_POTENTIAL_CLIENT,
                    },
                )
                pipedrive_person_id = pd_person.get("id")
                logger.info(
                    "pipedrive_person_created",
                    pipedrive_person_id=pipedrive_person_id,
                    full_name=full_name,
                )
            except Exception as pd_err:
                logger.warning(
                    f"Pipedrive create_person failed (continuing local-only): {pd_err}"
                )
        else:
            logger.warning("PIPEDRIVE_API_TOKEN not configured — registering client locally only")

        # 3. Create contact in local DB
        contact_result = await supabase.table("contacts").insert({
            "pipedrive_person_id": pipedrive_person_id,
            "full_name": full_name,
            "email": email,
            "phone": phone,
            "contact_status": "potential_client",  # לקוח פוטנציאלי (canonical)
            "professional_domain": None,  # Will be updated later
            # Only mark as synced if Pipedrive actually accepted the person;
            # otherwise leave NULL so the regular sync picks it up later.
            "pipedrive_last_synced_at": datetime.utcnow().isoformat() if pipedrive_person_id else None,
        }).execute()

        if not contact_result.data:
            logger.error("contact_creation_failed")
            return {
                "status": "error",
                "message": "סליחה, קצת בעיה בשמירת הפרטים שלך",
            }

        contact_id = contact_result.data[0]["id"]
        logger.info(
            "contact_created",
            contact_id=contact_id,
            phone=phone,
        )

        # 4. Update pandi_client to link to this contact
        await supabase.table("pandi_clients").update({
            "contact_id": contact_id,
            "identified_at": datetime.utcnow().isoformat(),
            "identification_method": "manual_intake_via_bot",
        }).eq("id", str(pandi_client_id)).execute()

        # 5. Send admin notification via Resend
        from pandapower.agents.pandi.notification_service import NotificationService

        notifier = NotificationService()
        await notifier.notify_new_client_prospect(
            client_name=full_name,
            email=email,
            phone=phone,
            company_name=company_name,
            role=role,
            conversation_id=str(conversation_id),
        )

        logger.info(
            "new_client_created_and_notified",
            contact_id=contact_id,
            pandi_client_id=str(pandi_client_id),
            phone=phone,
        )

        return {
            "status": "success",
            "contact_id": contact_id,
            "pipedrive_person_id": pipedrive_person_id,
            "message": f"✅ בחזקה! שמרתי את הפרטים שלך ופנדה-טק כבר מודעת ללקוח החדש. עכשיו בואו נדבר על המשרה שלך.",
        }

    except Exception as e:
        logger.error(f"create_client failed: {e}", exc_info=True)
        return {
            "status": "error",
            "message": "סליחה, קצת בעיה בשמירת הפרטים",
            "error": str(e),
        }


async def _resolve_candidate(supabase, candidate_number: str) -> Optional[dict]:
    """Load a candidate by its iron number (candidate_number), falling back to id.

    Returns the full set of fields ``build_cv_html`` consumes, or None.
    """
    cols = (
        "id, candidate_number, name, years_of_experience, clearance_level, "
        "extracted_from_cv, experiences, top_education, key_skills"
    )
    res = await supabase.table("candidates").select(cols).eq(
        "candidate_number", candidate_number
    ).limit(1).execute()
    if res.data:
        return res.data[0]
    # Fallback: the value may be a raw row id (candidate not yet backfilled).
    try:
        res = await supabase.table("candidates").select(cols).eq(
            "id", candidate_number
        ).limit(1).execute()
    except Exception:
        return None
    return res.data[0] if res.data else None


async def handle_send_candidate_cv(
    conversation_id: UUID,
    pandi_client_id: UUID,
    candidate_number: str,
    confirmation_note: Optional[str] = None,
) -> dict[str, Any]:
    """Auto-send the chosen candidate's full CV in Panda-Tech format.

    Called once the client has explicitly confirmed they want candidate
    ``candidate_number``. Renders the branded Panda-Tech CV (never the raw
    upload), delivers it to the client over WhatsApp, and records it on the
    referral. No human-approval gate (Pandi auto-send, per product decision).
    """
    try:
        supabase = await get_supabase_client()

        cand = await _resolve_candidate(supabase, candidate_number)
        if not cand:
            return {
                "status": "error",
                "message": f"סליחה, לא מצאתי את המועמד {candidate_number}",
            }
        candidate_id = cand.get("id")
        iron = cand.get("candidate_number") or str(candidate_id)

        # GUARD: only ever send a candidate we actually presented to THIS client
        # in THIS conversation. Without this, a hallucinated/typo'd number could
        # push a real-name full CV of the wrong candidate to the client.
        _guard = await supabase.table("candidate_referrals").select(
            "id, status, full_cv_sent_at"
        ).eq("conversation_id", str(conversation_id)).eq(
            "candidate_id", str(candidate_id)
        ).limit(1).execute()
        referral_row = _guard.data[0] if _guard.data else None
        if not referral_row:
            logger.warning(
                "send_cv_blocked_not_presented",
                candidate_number=iron,
                conversation_id=str(conversation_id),
            )
            return {
                "status": "error",
                "message": (
                    "המועמד הזה לא הוצג בשיחה הזו, אז אי אפשר לשלוח את קורות החיים שלו. "
                    "הצג/י את רשימת המועמדים ובקש/י מהלקוח לבחור מתוכה."
                ),
            }
        # Idempotency: if already delivered, don't re-send the file.
        if referral_row.get("full_cv_sent_at"):
            return {
                "status": "success",
                "candidate_number": iron,
                "message": f"כבר שלחתי ללקוח את קורות החיים של {iron} קודם לכן. ✅",
            }

        # 1. Render + upload the Panda-Tech formatted CV (shared with Elad).
        from pandapower.agents.shared.cv_delivery import (
            render_and_upload_cv,
            send_cv_file_via,
        )
        rendered = await render_and_upload_cv(
            supabase, cand, iron, folder=candidate_id
        )
        if not rendered.get("ok"):
            logger.error(
                "pandi_cv_render_failed",
                candidate_number=iron,
                error=rendered.get("error"),
            )
            return {
                "status": "error",
                "message": "סליחה, הייתה תקלה בהפקת קורות החיים. נסי שוב בעוד רגע.",
            }
        storage_path = rendered["path"]

        # 2. Resolve the client's WhatsApp chat.
        _pc = await supabase.table("pandi_clients").select(
            "phone, whatsapp_chat_id"
        ).eq("id", str(pandi_client_id)).limit(1).execute()
        pc = _pc.data[0] if _pc.data else {}
        chat_id = pc.get("whatsapp_chat_id")
        if not chat_id:
            from pandapower.core import phone as phone_utils
            chat_id = phone_utils.to_chat_id(pc.get("phone"))
        if not chat_id:
            return {
                "status": "error",
                "message": "סליחה, לא הצלחתי לאתר את ערוץ השליחה. צוות הגיוס יחזור אליך.",
            }

        # 3. Send via Pandi's Green API instance.
        from pandapower.integrations.green_api import get_green_api_client
        green_api = await get_green_api_client("pandi")
        if not green_api:
            return {
                "status": "error",
                "message": "סליחה, שירות השליחה אינו זמין כרגע. צוות הגיוס יחזור אליך.",
            }
        filename = f"PandaTech_CV_{iron}.pdf"
        try:
            sent = await send_cv_file_via(
                supabase, green_api, chat_id, storage_path, filename
            )
        finally:
            await green_api.close()

        if not sent:
            return {
                "status": "error",
                "message": "סליחה, השליחה נכשלה. צוות הגיוס יחזור אליך בהקדם.",
            }

        # 3b. Record the file as a message so the conversations screen shows a
        #     "CV sent" marker and we have a delivery record. Best-effort: the
        #     pandi_messages schema may lack file columns — drop them on failure.
        for _payload in (
            {
                "conversation_id": str(conversation_id),
                "pandi_client_id": str(pandi_client_id),
                "direction": "outbound",
                "message_type": "file",
                "text": filename,
            },
            {
                "conversation_id": str(conversation_id),
                "pandi_client_id": str(pandi_client_id),
                "direction": "outbound",
                "message_type": "text",
                "text": f"📄 קורות חיים מלאים נשלחו: {iron}",
            },
        ):
            try:
                await supabase.table("pandi_messages").insert(_payload).execute()
                break
            except Exception:
                continue

        # 4. Record delivery on the referral (direct update — bypasses the strict
        #    transition validator since auto-send skips the approval hops).
        try:
            await supabase.table("candidate_referrals").update({
                "status": "full_cv_sent",
                "formatted_cv_path": storage_path,
                "full_cv_sent_at": datetime.utcnow().isoformat(),
                "status_updated_at": datetime.utcnow().isoformat(),
            }).eq("id", referral_row["id"]).execute()
        except Exception as e:
            logger.warning(f"could not stamp referral cv_sent for {iron}: {e}")

        logger.info(
            "pandi_cv_sent",
            candidate_number=iron,
            conversation_id=str(conversation_id),
            path=storage_path,
        )
        return {
            "status": "success",
            "candidate_number": iron,
            "message": f"📄 שלחתי לך כעת את קורות החיים המלאים של {iron} בפורמט פנדה-טק. אשמח לתאם איתך את ההמשך!",
        }

    except Exception as e:
        logger.error(f"send_candidate_cv failed: {e}", exc_info=True)
        return {
            "status": "error",
            "message": "סליחה, הייתה תקלה בשליחת קורות החיים",
            "error": str(e),
        }


# Tool dispatcher
TOOL_HANDLERS = {
    "update_job_context": handle_update_job_context,
    "search_candidates": handle_search_candidates,
    "mark_client_interested": handle_mark_client_interested,
    "send_candidate_cv": handle_send_candidate_cv,
    "check_referral_history": handle_check_referral_history,
    "request_quota_increase": handle_request_quota_increase,
    "transfer_to_recruitment": handle_transfer_to_recruitment,
    "identify_client": handle_identify_client,
    "create_client": handle_create_client,
}


async def execute_tool(
    tool_name: str,
    tool_input: dict,
    conversation_id: UUID,
    pandi_client_id: UUID,
) -> dict[str, Any]:
    """Execute a tool by name with the given input.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        conversation_id: UUID of conversation
        pandi_client_id: UUID of Pandi client

    Returns:
        Tool execution result
    """
    handler = TOOL_HANDLERS.get(tool_name)

    if not handler:
        logger.error(f"Unknown tool: {tool_name}")
        return {"status": "error", "message": f"Unknown tool: {tool_name}"}

    try:
        # Call handler with conversation/client IDs and tool inputs
        result = await handler(
            conversation_id=conversation_id,
            pandi_client_id=pandi_client_id,
            **tool_input,
        )
        return result
    except Exception as e:
        logger.error(f"Tool execution failed: {tool_name}: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"סליחה, קצת בעיה בביצוע הפעולה",
            "error": str(e),
        }
