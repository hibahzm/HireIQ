"""HTML email templates for candidate-facing notifications.

Kept separate from ``NotificationService`` so the service stays focused on
*sending* (backend selection, dedup) while this module owns *presentation*.
Every template shares one responsive table layout and returns ``(subject, html)``.
"""

from __future__ import annotations

_BRAND = "HireIQ"
_PRIMARY = "#2563eb"
_INK = "#111827"
_BODY = "#374151"
_MUTED = "#9ca3af"


def _layout(
    *,
    heading: str,
    paragraphs: list[str],
    cta_label: str | None = None,
    cta_url: str | None = None,
    footnote: str = "If you did not apply for this role, you can safely ignore this email.",
) -> str:
    """Render the shared branded shell around per-email content."""
    body_blocks = "".join(
        f'<p style="margin:0 0 14px;color:{_BODY};font-size:15px;line-height:1.6;">{p}</p>'
        for p in paragraphs
    )
    cta_html = ""
    if cta_label and cta_url:
        cta_html = f"""
          <table cellpadding="0" cellspacing="0" style="margin:8px 0 4px;">
            <tr><td style="background:{_PRIMARY};border-radius:6px;">
              <a href="{cta_url}"
                 style="display:inline-block;padding:14px 28px;color:#ffffff;font-size:15px;font-weight:600;text-decoration:none;">
                {cta_label}
              </a>
            </td></tr>
          </table>"""
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f9fafb;padding:40px 0;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
        <tr><td style="background:{_PRIMARY};padding:32px 40px;">
          <h1 style="margin:0;color:#ffffff;font-size:22px;font-weight:700;">{_BRAND}</h1>
        </td></tr>
        <tr><td style="padding:40px;">
          <h2 style="margin:0 0 16px;color:{_INK};font-size:20px;">{heading}</h2>
          {body_blocks}
          {cta_html}
          <p style="margin:32px 0 0;color:{_MUTED};font-size:13px;">{footnote}</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def invitation_email(*, interview_link: str, expiry_hours: int) -> tuple[str, str]:
    """Sent when a candidate's CV is qualified — carries the interview link."""
    subject = "You're invited to your HireIQ interview"
    html = _layout(
        heading="Congratulations — you're invited to interview",
        paragraphs=[
            "Great news! After reviewing your application, we'd like to invite you to "
            "complete your interview with Sila, our AI interviewer.",
            "You can take the interview whenever you're ready — it runs in your browser, "
            "no installation needed. Find a quiet spot and allow about 15 minutes.",
            f"<strong>This invitation link is valid for {expiry_hours} hours.</strong> "
            "Please complete your interview before it expires.",
        ],
        cta_label="Start my interview →",
        cta_url=interview_link,
    )
    return subject, html


def rejection_email(*, job_title: str) -> tuple[str, str]:
    """Sent when a candidate's CV is not qualified — warm, future-facing."""
    subject = f"Update on your application — {job_title}"
    html = _layout(
        heading="Thank you for applying",
        paragraphs=[
            f"Thank you for your interest in the <strong>{job_title}</strong> role and for "
            "taking the time to apply. We truly appreciate it.",
            "After careful review, we won't be moving forward with your application for this "
            "particular position. This decision reflects the specific needs of this role and "
            "is not a judgement of your abilities or potential.",
            "We were genuinely glad to learn about your background, and we'd love to stay in "
            "touch. We'll keep your details on file and encourage you to apply for future "
            "openings that match your experience.",
            "We wish you every success in your job search and beyond.",
        ],
    )
    return subject, html


def interview_advance_email(*, job_title: str) -> tuple[str, str]:
    """Sent after a successful interview — team will follow up on next steps."""
    subject = f"Great interview! Next steps — {job_title}"
    html = _layout(
        heading="Thank you for completing your interview",
        paragraphs=[
            f"Thank you for completing your interview for the <strong>{job_title}</strong> role. "
            "We really enjoyed learning more about you.",
            "We're pleased to let you know that our team will be reviewing your interview and "
            "will be in touch shortly regarding the next steps in the process.",
            "There's nothing you need to do right now — just keep an eye on your inbox. "
            "Thank you for your time and enthusiasm.",
        ],
    )
    return subject, html


def feedback_email(*, job_title: str, feedback_url: str) -> tuple[str, str]:
    """Sent after an unsuccessful/uncertain interview — feedback & growth tips."""
    subject = f"Your interview feedback — {job_title}"
    html = _layout(
        heading="Your feedback is ready",
        paragraphs=[
            f"Thank you for interviewing for the <strong>{job_title}</strong> role and for the "
            "effort you put in.",
            "While we won't be progressing your application for this position, we believe "
            "feedback is one of the most valuable things we can offer. Your personalised report "
            "covers how you performed across each dimension, with concrete strengths and "
            "practical tips for areas you can keep developing.",
            "The link below is valid for <strong>30 days</strong> and does not require an account.",
        ],
        cta_label="View my feedback report →",
        cta_url=feedback_url,
    )
    return subject, html
