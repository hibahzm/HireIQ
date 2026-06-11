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

    async def send_user_invite_email(self, to_email: str, invite_link: str) -> None:
        if not await self._should_send("user_invite", to_email):
            return
        subject = "You've been invited to HireIQ"
        body = (
            f"You've been added as a team member on HireIQ. "
            f"Set your password here (link valid 24 hours): {invite_link}"
        )
        await self._send(to_email, subject, body)
        await self._mark_sent("user_invite", to_email)

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
        html_body = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f9fafb;padding:40px 0;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
        <tr><td style="background:#2563eb;padding:32px 40px;">
          <h1 style="margin:0;color:#ffffff;font-size:22px;font-weight:700;">HireIQ</h1>
        </td></tr>
        <tr><td style="padding:40px;">
          <h2 style="margin:0 0 16px;color:#111827;font-size:20px;">Your feedback is ready</h2>
          <p style="margin:0 0 12px;color:#374151;font-size:15px;line-height:1.6;">
            Thank you for interviewing for <strong>{job_title}</strong>.
            Your personalised feedback report — covering your performance across each evaluation
            dimension, along with strengths and areas for growth — is now available.
          </p>
          <p style="margin:0 0 28px;color:#374151;font-size:15px;line-height:1.6;">
            The link below is valid for <strong>30 days</strong> and does not require an account.
          </p>
          <table cellpadding="0" cellspacing="0">
            <tr><td style="background:#2563eb;border-radius:6px;">
              <a href="{feedback_url}"
                 style="display:inline-block;padding:14px 28px;color:#ffffff;font-size:15px;font-weight:600;text-decoration:none;">
                View my feedback report →
              </a>
            </td></tr>
          </table>
          <p style="margin:32px 0 0;color:#9ca3af;font-size:13px;">
            If you did not apply for this role, you can safely ignore this email.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
        await self._send_html(candidate_email, subject, html_body)
        await self._mark_sent("feedback", candidate_email)

    async def _send(self, to: str, subject: str, body: str) -> None:
        if self._settings.EMAIL_BACKEND == "resend":
            await self._send_resend(to, subject, text=body)
        else:
            logger.info("email.console", to=to, subject=subject, body=body)

    async def _send_html(self, to: str, subject: str, html: str) -> None:
        if self._settings.EMAIL_BACKEND == "resend":
            await self._send_resend(to, subject, html=html)
        else:
            logger.info("email.console", to=to, subject=subject, body="[HTML email]")

    async def _send_resend(
        self, to: str, subject: str, text: str = "", html: str = ""
    ) -> None:
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
