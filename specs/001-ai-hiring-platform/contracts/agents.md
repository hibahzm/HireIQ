# Internal Agents Service Contract

**Service**: `agents/` | **Base URL**: `http://agents:8001` (internal only)

This service is **not publicly reachable**. Only the `api` service calls it. All requests must include the shared secret header:

```
X-Internal-Secret: <AGENTS_INTERNAL_SECRET from config>
```

Requests missing or with an invalid header return `401`.

---

## Health

### `GET /health`

```json
{ "status": "ok" }
```

---

## Job Setup

### `POST /agents/job-setup/turn`

Advances the AI-guided job setup conversation one turn.

**Request**:
```json
{
  "job_id": "uuid",
  "company_id": "uuid",
  "conversation_history": [
    {"role": "assistant", "content": "Let's set up your job. What's the job title?"},
    {"role": "user", "content": "Senior Backend Engineer"}
  ],
  "user_message": "We need strong Python and PostgreSQL skills, 3+ years experience."
}
```

**Response 200**:
```json
{
  "message": "Got it. Are these hard requirements or nice-to-haves?",
  "status": "in_progress",
  "criteria_draft": null
}
```

When all criteria are elicited:
```json
{
  "message": "Here's the criteria summary — please confirm to activate the job.",
  "status": "completed",
  "criteria_draft": {
    "required_skills": [{"skill": "Python", "priority": "required"}, {"skill": "PostgreSQL", "priority": "required"}],
    "optional_skills": [],
    "experience_level": "senior",
    "min_years_experience": 3,
    "evaluation_dimensions": [
      {"name": "Technical Depth", "weight": 0.4, "description": "..."},
      {"name": "Problem Solving", "weight": 0.35, "description": "..."},
      {"name": "Communication", "weight": 0.25, "description": "..."}
    ],
    "dealbreakers": [],
    "min_screening_score": 60
  }
}
```

---

## CV Screening

### `POST /agents/cv-screen`

Screens a CV against job criteria. Returns a score, rationale, and status.

**Request**:
```json
{
  "application_id": "uuid",
  "company_id": "uuid",
  "cv_text": "Jane Doe\nSenior Software Engineer...",
  "job_criteria": {
    "required_skills": [...],
    "optional_skills": [...],
    "experience_level": "senior",
    "evaluation_dimensions": [...],
    "dealbreakers": [...],
    "min_screening_score": 60
  },
  "hybrid_search_results": [
    {"chunk_text": "...", "rrf_score": 0.92},
    {"chunk_text": "...", "rrf_score": 0.78}
  ]
}
```

`hybrid_search_results` are the top-10 RRF-merged results from the vector search performed by the api service before calling this endpoint.

**Response 200**:
```json
{
  "score": 82,
  "rationale": "Candidate has 6 years of Python experience and PostgreSQL expertise...",
  "status": "qualified",
  "guardrail_triggered": false
}
```

All text in `rationale` has been PII-redacted before this response is returned.

**Response when guardrail triggered**:
```json
{
  "score": 0,
  "rationale": "[screening blocked by guardrail]",
  "status": "rejected",
  "guardrail_triggered": true,
  "guardrail_reason": "Input contained content violating safety policy"
}
```

---

## Interview Turn

### `POST /agents/interview/turn`

Processes one interview turn. The api service passes the full LangGraph state; the agents service returns an updated state and the AI response. The api service persists the state in Redis.

**Request**:
```json
{
  "session_id": "uuid",
  "company_id": "uuid",
  "application_id": "uuid",
  "candidate_input": "I led the migration of our monolith over 18 months...",
  "interview_state": {
    "turn_count": 3,
    "dimensions_covered": ["Technical Depth"],
    "dimensions_remaining": ["System Design", "Communication"],
    "conversation_history": [...],
    "job_criteria": {...}
  }
}
```

**Response 200**:
```json
{
  "ai_response": "That's interesting — how did you manage data consistency across services?",
  "updated_state": {
    "turn_count": 4,
    "dimensions_covered": ["Technical Depth"],
    "dimensions_remaining": ["System Design", "Communication"],
    "conversation_history": [...],
    "job_criteria": {...}
  },
  "session_complete": false,
  "dimensions_remaining": 2,
  "guardrail_triggered": false,
  "blocked_redirect": null
}
```

When a guardrail blocks the candidate input:
```json
{
  "ai_response": "Let's keep focused on your professional experience. Tell me about a challenging project.",
  "updated_state": { ... },
  "session_complete": false,
  "dimensions_remaining": 2,
  "guardrail_triggered": true,
  "blocked_redirect": "Let's keep focused on your professional experience. Tell me about a challenging project."
}
```

The api service checks `guardrail_triggered` and stores the turn with `is_blocked = true`, `content_text = '[blocked]'`.

When interview is complete:
```json
{
  "ai_response": "Thank you — that concludes the interview.",
  "updated_state": { ... },
  "session_complete": true,
  "dimensions_remaining": 0,
  "guardrail_triggered": false,
  "blocked_redirect": null
}
```

---

## Evaluation

### `POST /agents/evaluate`

Generates a full evaluation report from the interview transcript.

**Request**:
```json
{
  "application_id": "uuid",
  "company_id": "uuid",
  "cv_text": "Jane Doe\nSenior Software Engineer...",
  "job_criteria": { ... },
  "transcript": [
    {"turn_index": 0, "speaker": "ai", "content_text": "Tell me about your distributed systems experience."},
    {"turn_index": 1, "speaker": "candidate", "content_text": "I led a Kafka-based event pipeline..."}
  ]
}
```

**Response 200**:
```json
{
  "overall_score": 88,
  "recommendation": "hire",
  "dimension_scores": [
    {
      "dimension": "Technical Depth",
      "score": 90,
      "evidence_quotes": ["Led a Kafka-based event pipeline handling 50k events/sec"]
    },
    {
      "dimension": "System Design",
      "score": 85,
      "evidence_quotes": ["Described sharding strategy for 500M-row table"]
    },
    {
      "dimension": "Communication",
      "score": 80,
      "evidence_quotes": ["Explained trade-offs clearly and concisely"]
    }
  ],
  "consistency_flags": [],
  "communication_quality": {
    "response_depth": 0.82,
    "filler_word_frequency": 0.03,
    "deflection_frequency": 0.05
  },
  "confidence_flag": false,
  "confidence_reason": null,
  "feedback_summary": {
    "strengths": "Excellent systems design knowledge with concrete examples...",
    "areas_for_improvement": "Could improve response conciseness in some answers..."
  }
}
```

All text fields have been PII-redacted before this response is returned.

**Confidence flag trigger**: Set to `true` when the average evidence quote count per dimension is < 1, or when the candidate gave predominantly one-word or deflecting answers (turn depth score < 0.3).
