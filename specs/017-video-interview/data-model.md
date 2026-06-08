# Data Model: Real-Time Streaming Voice Interview (Phase 1)

**One additive schema change.** Everything else is reused unchanged from the MVP interview.

## Changed entity

### `interview_sessions` (extended)

| Field | Type | Notes |
|-------|------|-------|
| `streaming_mode` | `BOOLEAN NOT NULL DEFAULT false` | **NEW.** When true, the WS uses the streaming branch; false (default) = existing turn-based path. Seeded at session creation from the **job-level streaming toggle** (FR-005). |

### Job streaming toggle (source of `streaming_mode`)

A job-level **`streaming_interview`** flag (default false), set during job setup, is the source that
seeds `interview_sessions.streaming_mode` when a session is created. Stored on the job (column or the
job's existing setup config); recruiters enable streaming per job.

- **Migration**: additive `streaming_mode` column with a server default, so existing rows and
  turn-based sessions are unaffected. No backfill required.
- All other `interview_sessions` fields (`status`, `mode`, `turn_count`, `max_turns`, `started_at`,
  `completed_at`, the 24-hour resume fields) are unchanged.

## Reused entities (unchanged)

| Entity | Role in streaming |
|--------|-------------------|
| `interview_messages` | Per-turn transcript with speaker attribution + audio references — written identically for streamed turns (FR-006 / SC-003). |
| Redis session state | `conversation_history`, `dimensions_covered/remaining`, `turn_count`, `max_turns` — reused as-is. |
| `audit_logs` | Existing interview-turn events; a streaming-fallback event is emitted if the streaming path degrades. |
| Audio blob storage | Candidate utterance audio stored as today — but in streaming the PCM frames are **assembled into a WAV and uploaded** so the message's `audio_blob_key` has parity with turn-based; AI turn references its synthesized audio. |

## Validation / invariants

- **Guardrail-before-response (FR-007)**: AI text comes only from `agents/interview/turn` (post-
  guardrail); TTS never synthesizes un-guardrailed text; blocked content is not stored.
- **Transcript parity (SC-003)**: a streamed interview produces the same `interview_messages` shape as
  a turn-based one (same turns, attribution, audio refs).
- **Fallback (FR-008)**: if streaming components are unavailable, the session continues turn-based and
  remains resumable for 24 h.
- **Tenant isolation**: session/messages are RLS-scoped by `company_id` (set on the WS connection).

## Out of scope

- No new tables or entities; no change to `interview_messages`, evaluation, or transcript shape.
- No barge-in state (half-duplex in V2-3).
