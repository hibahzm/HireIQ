import { describe, expect, it } from "vitest";
import { SilenceTracker } from "./vad";

const FRAME_MS = 100;
const SPEECH = 0.9;
const SILENCE = 0.1;

describe("SilenceTracker (end-of-speech logic, SC-004 / FR-002)", () => {
  it("fires end_of_speech after a sustained silence following speech", () => {
    const t = new SilenceTracker({ silenceMs: 800 });
    expect(t.update(SPEECH, FRAME_MS)).toBe("speech");
    // 7 silent frames = 700ms < 800ms → not yet
    let last = "";
    for (let i = 0; i < 7; i++) last = t.update(SILENCE, FRAME_MS);
    expect(last).toBe("silence");
    // 8th silent frame reaches 800ms → end
    expect(t.update(SILENCE, FRAME_MS)).toBe("end_of_speech");
    expect(t.hasEnded).toBe(true);
  });

  it("does NOT end the turn on a short mid-sentence pause", () => {
    const t = new SilenceTracker({ silenceMs: 800 });
    t.update(SPEECH, FRAME_MS);
    // 3 silent frames (300ms) — a natural pause
    for (let i = 0; i < 3; i++) expect(t.update(SILENCE, FRAME_MS)).toBe("silence");
    // resume speaking — silence accumulator resets
    expect(t.update(SPEECH, FRAME_MS)).toBe("speech");
    // another 7 frames of silence still < 800ms from the reset
    let last = "";
    for (let i = 0; i < 7; i++) last = t.update(SILENCE, FRAME_MS);
    expect(last).toBe("silence");
    expect(t.hasEnded).toBe(false);
  });

  it("ignores leading silence before any speech", () => {
    const t = new SilenceTracker({ silenceMs: 800 });
    // 20 silent frames before the candidate speaks → never ends
    for (let i = 0; i < 20; i++) expect(t.update(SILENCE, FRAME_MS)).toBe("silence");
    expect(t.hasEnded).toBe(false);
  });

  it("reset() allows a fresh utterance", () => {
    const t = new SilenceTracker({ silenceMs: 800 });
    t.update(SPEECH, FRAME_MS);
    for (let i = 0; i < 8; i++) t.update(SILENCE, FRAME_MS);
    expect(t.hasEnded).toBe(true);
    t.reset();
    expect(t.hasEnded).toBe(false);
    expect(t.update(SPEECH, FRAME_MS)).toBe("speech");
  });
});
