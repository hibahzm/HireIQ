from __future__ import annotations

import hashlib
from datetime import date

import structlog

logger = structlog.get_logger()

_DEDUP_TTL = 86400  # 24 hours


class NotificationService:
    def __init__(self, redis=None) -> None:
        self._redis = redis
        from app.config import get_settings
        self._settings = get_settings()

    async def send_confirmation_email(self, candidate_email: str, job_title: str) -> None:
        if not await self._should_send("confirmation", candidate_email):
            return
        subject = f"Application received — {job_title}"
        body = f"Thank you for applying for {job_title}. We'll be in touch soon."
        await self._send(candidate_email, subject, body)
        await self._mark_sent("confirmation", candidate_email)

    async def send_invitation_email(self, candidate_email: str, interview_link: str) -> None:
        if not await self._should_send("invitation", candidate_email):
            return
        subject = "You're invited to an interview"
        body = f"Congratulations! You've been selected for an interview. Click here to begin: {interview_link}"
        await self._send(candidate_email, subject, body)
        await self._mark_sent("invitation", candidate_email)

    async def send_feedback_email(
        self, candidate_email: str, job_title: str, feedback_url: str
    ) -> None:
        if not await self._should_send("feedback", candidate_email):
            return
        subject = f"Your interview feedback — {job_title}"
        body = f"Your feedback report is ready. View it here: {feedback_url}"
        await self._send(candidate_email, subject, body)
        await self._mark_sent("feedback", candidate_email)

    async def _send(self, to: str, subject: str, body: str) -> None:
        if self._settings.EMAIL_BACKEND == "resend":
            await self._send_resend(to, subject, body)
        else:
            logger.info(
                "email.console",
                to=to,
                subject=subject,
                body=body[:100],
            )

    async def _send_resend(self, to: str, subject: str, body: str) -> None:
        import resend
        resend.api_key = self._settings.EMAIL_API_KEY
        resend.Emails.send({
            "from": self._settings.EMAIL_FROM,
            "to": [to],
            "subject": subject,
            "text": body,
        })

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
