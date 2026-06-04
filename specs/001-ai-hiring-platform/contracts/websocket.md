# WebSocket Contract: Voice Interview

**Endpoint**: `WS /interviews/{interview_token}/connect`

**Transport**: WebSocket (RFC 6455), turn-based (not streaming). The candidate sends one complete turn; the server responds with one complete AI turn. Both sides wait before sending the next message.

**Authentication**: The `interview_token` path parameter is the sole authenticator. No JWT or cookie is required — candidates have no accounts. The token is validated against `applications.interview_token` on connection.

---

## Connection Handshake

1. Client opens WebSocket to `ws://localhost:8000/interviews/{token}/connect`
2. Server validates the token:
   - Looks up the application by `interview_token`
   - Checks `interview_token_expires_at > now()`
   - Checks session status is not `completed` or `abandoned`
3. On success: server sends `session_ready` message; connection is established
4. On failure: server closes connection with appropriate close code (see Errors below)

**`session_ready` message** (server → client, on successful connect):
```json
{
  "type": "session_ready",
  "session_id": "uuid",
  "mode": "voice",
  "turn_count": 0,
  "max_turns": 20,
  "resuming": false
}
```
When resuming an interrupted session:
```json
{
  "type": "session_ready",
  "session_id": "uuid",
  "mode": "voice",
  "turn_count": 7,
  "max_turns": 20,
  "resuming": true,
  "last_ai_message": "Let's continue from where we left off. You were describing your experience with database optimization..."
}
```

---

## Message Types

### Client → Server

#### `audio_input`

Candidate submits a voice response (complete turn, not streaming chunks).

```json
{
  "type": "audio_input",
  "data": "<base64-encoded audio, WAV or WebM>",
  "duration_ms": 8500
}
```

- Audio is transcribed server-side via OpenAI Whisper API (`whisper-1`)
- Transcript is passed through the guardrail registry before being stored or forwarded to the agent
- `duration_ms` is used for quality heuristics (very short = may be empty/noise)

---

#### `text_input`

Candidate submits a text response (fallback mode, FR-018).

```json
{
  "type": "text_input",
  "content": "I led the migration of our monolith to a microservices architecture over 18 months."
}
```

---

#### `ping`

Keepalive from client. Server responds with `pong`. Sent every 30 seconds when no turn is in progress.

```json
{ "type": "ping" }
```

---

### Server → Client

#### `ai_turn`

AI response to the candidate's input. Includes synthesized audio.

```json
{
  "type": "ai_turn",
  "turn_index": 3,
  "text": "That's interesting — how did you handle data consistency across services during the migration?",
  "audio": "<base64-encoded MP3>",
  "dimensions_remaining": 2
}
```

- `text` is always present (accessibility fallback)
- `audio` is always present in voice mode; generated via OpenAI TTS (`tts-1`) with Azure AI Speech as fallback
- `dimensions_remaining` is the count of evaluation dimensions not yet adequately explored; used by the frontend to show progress

---

#### `turn_processing`

Acknowledges receipt of candidate input; signals that the server is processing. Client should show a "thinking" indicator.

```json
{ "type": "turn_processing", "turn_index": 3 }
```

---

#### `turn_blocked`

Emitted when the guardrail registry blocks a candidate input (FR-023). The blocked content is not stored. The AI provides a safe redirect response.

```json
{
  "type": "turn_blocked",
  "turn_index": 3,
  "redirect_text": "Let's keep focused on your professional experience. Tell me about a challenging project you've led.",
  "redirect_audio": "<base64-encoded MP3>"
}
```

---

#### `interview_complete`

Emitted when all dimensions are explored OR max_turns is reached.

```json
{
  "type": "interview_complete",
  "turn_count": 14,
  "message": "Thank you for completing the interview. You'll receive feedback by email once your evaluation is ready."
}
```

After sending this message the server closes the WebSocket with close code `1000` (Normal Closure).

---

#### `session_expired`

Emitted if the candidate attempts to reconnect after the 24-hour resume window has passed.

```json
{
  "type": "session_expired",
  "message": "This interview session has expired. Please contact the recruiter if you'd like to reschedule."
}
```

---

#### `service_error`

Emitted when the AI agent service is unavailable mid-interview (FR-020b). Session is preserved as `system_interrupted` and remains resumable within the 24-hour window.

```json
{
  "type": "service_error",
  "message": "We're experiencing a technical issue. Your progress has been saved — you can reconnect using the same link to continue.",
  "resumable": true
}
```

Server closes the WebSocket with close code `1011` (Internal Error) after sending this message.

---

#### `pong`

Response to client `ping`.

```json
{ "type": "pong" }
```

---

## Session Lifecycle

```
Client connects
  → Server validates token
  → Server sends session_ready
  → [loop until complete or error]
       Client sends audio_input or text_input
       Server sends turn_processing
       Server processes (STT → guardrail → agent → TTS)
       Server sends ai_turn  OR  turn_blocked
  → Server sends interview_complete
  → Server closes (1000)
```

**On network drop**: Client may reconnect with the same token URL. If within 24h, server sends `session_ready` with `resuming: true` and continues from last completed turn.

**On AI service failure**: Server sends `service_error` and closes. Session status set to `system_interrupted`. Client may reconnect when service recovers (still within 24h window).

---

## WebSocket Close Codes

| Code | Meaning |
|---|---|
| 1000 | Normal closure (interview completed) |
| 1008 | Policy violation (invalid token, expired token, session already completed) |
| 1011 | Internal error (AI service unavailable) |

---

## Audio Specifications

**Input** (client → server):
- Format: WAV (PCM 16-bit, mono, 16 kHz) or WebM Opus
- Max duration: 3 minutes per turn
- Max size: 10 MB per turn

**Output** (server → client):
- Format: MP3 (base64-encoded in JSON payload)
- Generated by: OpenAI TTS `tts-1` (primary), Azure AI Speech (fallback)
- Voice: `onyx` (configurable per job in future versions)
