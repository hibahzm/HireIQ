from __future__ import annotations

import hashlib
from datetime import date

import structlog

from app.services import email_templates

logger = structlog.get_logger()

_DEDUP_TTL = 86400  # 24 hours


class NotificationService:
    def __init__(self, redis=None) -> None:
        self._redis = redis
        from app.config import get_settings

        self._settings = get_settings()

    async def send_user_invite_email(self, to_email: str, invite_link: str) -> None:
        """Admin invited a team member → branded set-password email (24h link)."""
        if not await self._should_send("user_invite", to_email):
            return
        subject, html = email_templates.team_invite_email(invite_link=invite_link, expiry_hours=24)
        await self._send_html(to_email, subject, html)
        await self._mark_sent("user_invite", to_email)

    async def send_invitation_email(
        self, candidate_email: str, interview_link: str, expiry_hours: int | None = None
    ) -> None:
        """CV qualified → invite the candidate to interview (link is time-limited)."""
        if not await self._should_send("invitation", candidate_email):
            return
        hours = expiry_hours or self._settings.INTERVIEW_LINK_EXPIRY_HOURS
        subject, html = email_templates.invitation_email(
            interview_link=interview_link, expiry_hours=hours
        )
        await self._send_html(candidate_email, subject, html)
        await self._mark_sent("invitation", candidate_email)

    async def send_password_reset_email(self, to_email: str, reset_link: str) -> None:
        """Forgot-password reset link. No daily dedup — a user may legitimately
        request a reset more than once a day."""
        subject, html = email_templates.password_reset_email(reset_link=reset_link, expiry_hours=1)
        await self._send_html(to_email, subject, html)

    async def send_rejection_email(self, candidate_email: str, job_title: str) -> None:
        """CV not qualified → warm rejection that invites future applications."""
        if not await self._should_send("rejection", candidate_email):
            return
        subject, html = email_templates.rejection_email(job_title=job_title)
        await self._send_html(candidate_email, subject, html)
        await self._mark_sent("rejection", candidate_email)

    async def send_interview_advance_email(self, candidate_email: str, job_title: str) -> None:
        """Interview succeeded → tell the candidate the team will follow up."""
        if not await self._should_send("advance", candidate_email):
            return
        subject, html = email_templates.interview_advance_email(job_title=job_title)
        await self._send_html(candidate_email, subject, html)
        await self._mark_sent("advance", candidate_email)

    async def send_feedback_email(
        self, candidate_email: str, job_title: str, feedback_url: str
    ) -> None:
        """Interview unsuccessful/uncertain → feedback report with growth tips."""
        if not await self._should_send("feedback", candidate_email):
            return
        subject, html = email_templates.feedback_email(
            job_title=job_title, feedback_url=feedback_url
        )
        await self._send_html(candidate_email, subject, html)
        await self._mark_sent("feedback", candidate_email)

    async def _send_html(self, to: str, subject: str, html: str) -> None:
        if self._settings.EMAIL_BACKEND == "resend":
            await self._send_resend(to, subject, html=html)
        else:
            logger.info("email.console", to=to, subject=subject, body="[HTML email]")

    async def _send_resend(self, to: str, subject: str, text: str = "", html: str = "") -> None:
        import resend

        resend.api_key = self._settings.EMAIL_API_KEY
        payload: dict = {
            "from": self._settings.EMAIL_FROM,
            "to": [to],
            "subject": subject,
        }
        if html:
            payload["html"] = html
        else:
            payload["text"] = text
        resend.Emails.send(payload)

    def _dedup_key(self, template: str, recipient: str) -> str:
        day = date.today().isoformat()
        h = hashlib.sha256(recipient.encode()).hexdigest()[:16]
        return f"email:dedup:{template}:{h}:{day}"

    async def _should_send(self, template: str, recipient: str) -> bool:
        if self._redis is None:
            return True
        key = self._dedup_key(template, recipient)
        return not bool(await self._redis.get(key))

    async def _mark_sent(self, template: str, recipient: str) -> None:
        if self._redis is None:
            return
        key = self._dedup_key(template, recipient)
        await self._redis.set(key, "1", ex=_DEDUP_TTL)
