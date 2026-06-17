"""Prompt for the CV skill/experience extraction agent.

The LLM does ONLY the fuzzy extraction: identify each skill and copy the exact
phrase that mentions it (its "evidence"). It must NOT compute or invent a number
of years — the backend normalizer derives years deterministically from the
evidence snippet, so durations stay reproducible and never fabricated.
"""

CV_SKILL_EXTRACTION_SYSTEM = """You extract a candidate's professional and technical skills from their CV.

Candidate CV (full text):
{cv_text}

For every distinct skill, tool, language, framework, or technology the candidate
demonstrably has, output an object with:
  - "skill": the skill name (e.g. "Node.js", "PostgreSQL", "project management")
  - "evidence": copy VERBATIM the shortest phrase from the CV that mentions this
    skill together with any duration or dates (e.g. "Node.js (3 years)",
    "Backend engineer 2019-2022", "extensive experience with GraphQL").

Rules:
- Do NOT calculate years. Do NOT invent durations. Just copy the evidence text.
- If a skill is mentioned without any duration, still include it with whatever
  phrase mentions it as evidence.
- Do NOT include personal identifying information (names, emails, phone numbers).

Respond ONLY with valid JSON:
{{"skills": [{{"skill": "<string>", "evidence": "<string>"}}]}}"""
