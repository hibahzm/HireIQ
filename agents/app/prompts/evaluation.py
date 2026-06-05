"""Prompts for the evaluation agent."""

EVALUATION_SCORE_DIMENSIONS = """You are an expert hiring assessor evaluating a candidate's interview performance.

Job criteria and evaluation dimensions:
{criteria}

Interview transcript:
{transcript}

CV text (for context):
{cv_text}

Score EACH dimension defined in the job criteria on a 0-100 scale.
For each dimension provide 1-3 short evidence quotes directly from the transcript.

Respond ONLY with valid JSON:
{{
  "dimension_scores": [
    {{"dimension": "<name>", "score": <int 0-100>, "evidence_quotes": ["<quote1>", ...]}}
  ]
}}

Important:
- Evidence quotes must be verbatim short excerpts from the transcript (max 120 chars each).
- Remove any personally identifying information (names, emails, phone numbers) from quotes.
- If evidence is absent for a dimension set evidence_quotes to [].
"""

EVALUATION_FLAG_CONSISTENCY = """You are checking for consistency between a candidate's CV and their interview answers.

CV text:
{cv_text}

Interview transcript:
{transcript}

Identify any contradictions or unverified claims. Return an empty list if none found.

Respond ONLY with valid JSON:
{{
  "consistency_flags": [
    {{
      "claim": "<what was claimed>",
      "cv_statement": "<what CV says>",
      "interview_statement": "<what candidate said in interview>",
      "flag_type": "contradiction" | "unverified"
    }}
  ]
}}

Do NOT include any personally identifying information in the output.
"""

EVALUATION_SCORE_COMMUNICATION = """Analyse the communication quality of the following interview transcript.

Transcript:
{transcript}

Compute three metrics as floats between 0 and 1:
- response_depth: average substantiveness of answers (0=one-word/deflecting, 1=deep/elaborated)
- filler_word_frequency: ratio of filler words (um, uh, like, you know) to total words
- deflection_frequency: ratio of deflecting or evasive answers to total turns

Respond ONLY with valid JSON:
{{
  "communication_quality": {{
    "response_depth": <float>,
    "filler_word_frequency": <float>,
    "deflection_frequency": <float>
  }}
}}
"""

EVALUATION_ASSESS_CONFIDENCE = """Given the following evaluation data, decide whether to set a confidence flag.

Dimension scores and evidence:
{dimension_scores}

Communication quality:
{communication_quality}

Set confidence_flag to true if:
- The average number of evidence quotes per dimension is less than 1, OR
- response_depth < 0.3

When confidence_flag is true, write a 1-2 sentence confidence_reason explaining why.

Respond ONLY with valid JSON:
{{
  "confidence_flag": true | false,
  "confidence_reason": "<string or null>"
}}
"""

EVALUATION_GENERATE_SUMMARY = """Write a concise candidate feedback summary based on this evaluation.

Overall score: {overall_score}
Recommendation: {recommendation}
Dimension scores: {dimension_scores}
Consistency flags: {consistency_flags}
Communication quality: {communication_quality}

Write two short paragraphs:
1. Strengths (2-3 sentences)
2. Areas for improvement (2-3 sentences)

Do NOT include any personally identifying information (names, emails, phone numbers).

Respond ONLY with plain text in this format:
Strengths: <paragraph>
Areas for improvement: <paragraph>
"""
