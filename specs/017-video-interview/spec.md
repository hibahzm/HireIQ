# Feature Specification: Real-Time Streaming Voice Interview

**Feature Branch**: `017-video-interview`

**Created**: 2026-06-07

**Status**: Draft

**Input**: V2-3 — replace the turn-based voice model with real-time streaming voice

## Clarifications

### Session 2026-06-07

- Q: Which streaming STT/TTS stack should V2-3 use (guardrails must run between transcription and the AI response)? → A: Azure Speech SDK streaming on the **free F0 tier** — streaming recognition (STT) and streaming synthesis (TTS), reusing the already-configured Azure Speech credentials; the existing agent graph + guardrail registry stay between STT and TTS. (OpenAI Realtime rejected: bypasses the guardrail pipeline; OpenAI Whisper/TTS have no free tier and don't stream incrementally.)
- Q: Where is end-of-speech / voice-activity detection performed? → A: Client-side — the browser runs silero-vad (onnxruntime-web) over AudioWorklet-captured audio and streams detected speech to the backend.
- Q: Is barge-in (candidate interrupting the AI mid-response) in scope for V2-3? → A: Out of scope for V2-3 (half-duplex: mic ignored while AI audio plays); flagged as a recommended future enhancement if time permits.
- Q: How should SC-001 (~2 s end-of-speech → first audio) be measured? → A: p95 ≤ 2 s from end-of-speech to first audio chunk, tracked as a target metric (not a hard merge gate, given third-party speech-service variance).

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Candidate Has a Natural, Streaming Conversation (Priority: P1)

A candidate joins the interview and simply speaks — no record/stop button. The system
detects when they finish a thought (end-of-speech), transcribes it, the AI generates a
reply, and the AI's voice begins playing within a couple of seconds and streams in as
it is synthesized. The conversation feels like talking to a person rather than
exchanging walkie-talkie turns.

**Why this priority**: This is the entire point of V2-3 — eliminating the ~10-second
turn latency that makes the MVP interview feel mechanical.

**Independent Test**: Join an interview in streaming mode, speak continuously without
pressing any button, and confirm: end-of-speech is detected after a short silence, the
AI responds within ~2 seconds, audio starts before synthesis fully completes, and the
stored transcript is identical in structure to a turn-based interview.

**Acceptance Scenarios**:

1. **Given** a streaming-enabled interview, **When** the candidate speaks and then
   pauses, **Then** the system detects end-of-speech after a brief silence and begins
   generating a response without any button press.
2. **Given** the AI is responding, **When** synthesis begins, **Then** the candidate
   hears audio start before the full response has finished synthesizing (chunked
   playback).
3. **Given** a streaming interview completes, **When** the recruiter reviews it,
   **Then** the transcript is stored with the same per-turn attribution and audio
   references as a turn-based interview.
4. **Given** the candidate is mid-sentence with natural short pauses, **When** they
   continue speaking, **Then** the system does not prematurely cut them off (end-of-
   speech requires a sustained silence threshold).

---

### Edge Cases

- Background noise or a brief pause must not trigger a false end-of-turn; only a
  sustained silence (≥ the configured threshold) ends a turn.
- A network drop mid-stream falls back to the existing resumable-session behavior
  (24-hour resume window from the MVP).
- If streaming components fail, the session falls back to the turn-based path so the
  interview can still complete.
- Harmful/off-topic input is still blocked by the guardrails before any AI response,
  exactly as in turn-based mode; blocked content is not stored.
- A candidate who cannot use voice still has the text fallback (inherited from MVP).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The interview MUST support continuous microphone capture from the
  candidate without a manual record/stop action.
- **FR-002**: The system MUST detect end-of-speech automatically using **client-side**
  voice-activity detection (silero-vad via onnxruntime-web in the browser) after a
  sustained silence threshold (target ~800 ms) following speech; detected speech is
  streamed to the backend.
- **FR-003**: The system MUST transcribe candidate audio incrementally on the backend
  (Azure streaming recognition) and finalize the transcript when end-of-speech is
  detected; surfacing interim partial transcripts to the candidate UI is optional.
- **FR-004**: The system MUST stream the AI's synthesized voice back to the candidate
  in chunks (Azure Speech streaming synthesis) so playback can begin before synthesis
  completes.
- **FR-005**: Streaming mode MUST be selectable via a **job-level streaming toggle** set
  during job setup (default off), which seeds each new interview session's
  `streaming_mode`; when disabled, the system MUST use the existing turn-based path
  unchanged.
- **FR-006**: The full transcript MUST be stored identically to turn-based interviews
  (per-turn speaker attribution and audio references).
- **FR-007**: All candidate input MUST continue to pass through the guardrail registry
  before any AI response, and blocked content MUST NOT be stored (parity with MVP
  FR-023).
- **FR-008**: A streaming session that is interrupted MUST remain resumable within the
  existing 24-hour window, and the system MUST fall back to turn-based handling if
  streaming components are unavailable.

### Key Entities

- **Interview Session** (extended): gains a `streaming_mode` flag (default off) so
  existing turn-based sessions are unaffected.

## Success Criteria *(mandatory)*

- **SC-001**: Latency from end-of-speech to the first AI audio chunk is **p95 ≤ 2
  seconds**, tracked as a target metric (not a hard merge gate, given third-party
  speech-service variance). Note: this budget is dominated by the agent/LLM turn, so the
  STT-finalize→first-chunk and agent-call segments are measured separately.
- **SC-002**: AI audio playback starts before full synthesis completes for streamed
  responses.
- **SC-003**: A completed streaming interview stores a transcript indistinguishable in
  structure from a turn-based interview (same turns, attribution, audio).
- **SC-004**: End-of-speech detection does not prematurely cut off a candidate during
  natural mid-sentence pauses (no false-positive turn endings in normal speech).

## Assumptions

- The candidate's browser supports continuous audio capture (AudioWorklet) and
  chunked audio playback (MediaSource).
- Voice-activity detection runs **client-side** (silero-vad via onnxruntime-web); the
  backend uses **Azure Speech (free F0 tier)** for streaming STT and TTS.
- **Barge-in is out of scope for V2-3** — the session is half-duplex (the mic is
  ignored while AI audio plays). It is a recommended future enhancement if time permits.
- Streaming replaces the turn-based model for enabled jobs; turn-based remains the
  default and the fallback.
- English-language interviews only (inherited from MVP).

## Dependencies

- Builds on the MVP WebSocket interview (`InterviewService`, `SttService`,
  `TtsService`, `interview_graph`, `InterviewRoomPage`) and Redis session state.
- Adds **client-side** voice-activity detection (`silero-vad` via `onnxruntime-web` in
  the browser) and **Azure Speech SDK streaming STT/TTS (free F0 tier)** on the backend,
  reusing the existing Azure Speech credentials.
