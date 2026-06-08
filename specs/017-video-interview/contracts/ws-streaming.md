# WebSocket Contract: Streaming Voice Interview (Phase 1)

A **delta** on the existing interview socket `WS /interviews/{token}/connect`. Connection, auth,
session resume, and the turn-based `text_input` / `audio_input` messages are unchanged
([MVP interview contract](../../001-ai-hiring-platform/contracts/)). The streaming branch is active
only when the session's `streaming_mode` is true; otherwise the turn-based messages apply.

## Connection handshake (unchanged + one field)

On connect the server sends the existing `session_ready` payload, extended with:

```json
{ "type": "session_ready", "session_id": "uuid", "streaming_mode": true, "...": "..." }
```

The client uses `streaming_mode` to decide whether to start continuous capture + VAD or show the
turn-based controls.

## Client → Server (streaming branch)

| Message | Payload | When |
|---------|---------|------|
| `audio_frame` | `{ "type": "audio_frame", "audio": "<base64 PCM16 16kHz mono>" }` | Continuously while the client VAD reports speech. |
| `end_of_speech` | `{ "type": "end_of_speech" }` | Client VAD detects sustained silence (≥ ~800 ms) → finalize the utterance. |
| `text_input` | (unchanged) | Text fallback (accessibility / streaming unavailable). |

The client suspends sending `audio_frame` while AI audio is playing (half-duplex; no barge-in in V2-3).

## Server → Client (streaming branch)

| Message | Payload | When |
|---------|---------|------|
| `partial_transcript` | `{ "type": "partial_transcript", "text": "..." }` | Optional — incremental STT hypotheses before finalize. |
| `turn_processing` | (unchanged) | After `end_of_speech`, while the agent computes the reply. |
| `turn_blocked` | `{ "type": "turn_blocked", "message": "..." }` | Guardrail blocked the input — **no audio synthesized**, nothing stored (FR-007). |
| `ai_turn_text` | `{ "type": "ai_turn_text", "text": "..." }` | Final guardrail-approved AI text (for the transcript pane). |
| `ai_audio_chunk` | `{ "type": "ai_audio_chunk", "audio": "<base64 mp3 chunk>", "seq": N }` | Repeated as TTS synthesizes; client appends to a `MediaSource` SourceBuffer (`audio/mpeg`) and begins playback on the first chunk (FR-004 / SC-002). |
| `ai_audio_end` | `{ "type": "ai_audio_end" }` | Synthesis complete; client may resume capture. |
| `interview_complete` | (unchanged) | Session finished → triggers evaluation. |
| `service_error` | (unchanged) | On error; session preserved + resumable; client may fall back to turn-based (FR-008). |

## Invariants

- **Ordering**: `ai_audio_chunk` messages are delivered in `seq` order; `ai_turn_text` precedes or
  accompanies the first chunk.
- **Guardrails first (FR-007)**: no `ai_audio_chunk` is ever emitted for blocked input.
- **Latency (SC-001)**: `end_of_speech` → first `ai_audio_chunk` is tracked at p95 ≤ 2 s.
- **Parity (SC-003 / FR-006)**: the stored transcript after a streaming session is structurally
  identical to a turn-based one.
- **Fallback (FR-008)**: if streaming init fails, the server keeps the session on the turn-based
  messages; the client shows turn-based controls.
