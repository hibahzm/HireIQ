# Quickstart Validation: Streaming Voice Interview

Validates V2-3 end-to-end. Assumes the MVP stack is running (see the
[MVP quickstart](../../001-ai-hiring-platform/quickstart.md)) with Azure Speech (free F0 tier)
configured (`AZURE_SPEECH_KEY` / `AZURE_SPEECH_REGION`) and a job whose interview is
`streaming_mode`-enabled.

## Prerequisites

- Running stack (`docker compose -f infra/docker-compose.yml up -d`).
- Azure Speech F0 resource; `AZURE_SPEECH_KEY` / `AZURE_SPEECH_REGION` set via the config/secret path.
- A candidate interview link (`$TOKEN`) for a streaming-enabled session.
- A modern Chromium browser (AudioWorklet + MediaSource).

## Scenario 1 — Natural streaming conversation (US1 / SC-001 / SC-002)

1. Open the interview link and grant microphone access. Confirm there is **no record/stop button** —
   capture is continuous.
2. Speak a sentence, then stop.

**Expected**: after a brief silence the client detects end-of-speech (no button press), the AI
replies, and **audio begins within ~2 s (p95 ≤ 2 s target) and starts before synthesis completes**
(you hear the first words while the rest streams in).

## Scenario 2 — No premature cut-off (SC-004 / FR-002)

Speak with natural short mid-sentence pauses (e.g. "I worked at… a fintech startup… for three years").

**Expected**: the system does **not** end the turn during the short pauses; only a sustained silence
(≥ ~800 ms) finalizes the utterance.

## Scenario 3 — Transcript parity (SC-003 / FR-006)

Complete a streaming interview, then open the recruiter's evaluation/transcript view.

**Expected**: the stored transcript has the **same** per-turn speaker attribution and audio references
as a turn-based interview — structurally indistinguishable.

## Scenario 4 — Guardrails still block (FR-007)

Speak clearly harmful/off-topic content.

**Expected**: the turn is blocked **before** any AI audio is synthesized (`turn_blocked`, no
`ai_audio_chunk`); the blocked content is not stored.

## Scenario 5 — Fallback & resume (FR-008)

- Disable/break a streaming component (or use a browser without AudioWorklet) → the session falls back
  to the **turn-based** path and still completes.
- Drop the network mid-stream, then reconnect within 24 h → the session **resumes** (existing window).

## Scenario 6 — Streaming off by default (FR-005)

Open an interview for a job that is **not** streaming-enabled.

**Expected**: `streaming_mode` is false; the turn-based controls appear and behave exactly as in the MVP.

## Notes

- WebSocket message shapes: see [contracts/ws-streaming.md](contracts/ws-streaming.md).
- Latency measurement (end-of-speech → first `ai_audio_chunk`) is captured by the streaming check in
  `infra/perf/` for the SC-001 tracked target.
