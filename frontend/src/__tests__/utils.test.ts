import { describe, expect, it } from "vitest";
import {
  defaultModelName,
  fileSize,
  formatModelOption,
  groupTurns,
  markMatches,
  mmss,
  nearestSegment,
  parseMeetingHash,
  parseMeetingIdFromHash,
  percent,
} from "../utils";

describe("utils", () => {
  it("formats mmss durations properly", () => {
    expect(mmss(0)).toBe("00:00");
    expect(mmss(65)).toBe("01:05");
    expect(mmss(3600)).toBe("60:00");
    expect(mmss(-5)).toBe("00:00");
    expect(mmss(null)).toBe("00:00");
  });

  it("formats fileSize in human units", () => {
    expect(fileSize(0)).toBe("—");
    expect(fileSize(null)).toBe("—");
    expect(fileSize(512)).toBe("512 B");
    expect(fileSize(2048)).toBe("2.0 KB");
    expect(fileSize(5 * 1024 * 1024)).toBe("5.0 MB");
  });

  it("formats transcription progress percentage", () => {
    expect(percent(null)).toBe("");
    expect(
      percent({
        step: "Transcribing",
        step_number: 1,
        steps: 2,
        fraction: null,
        elapsed: 3,
      }),
    ).toBe("");
    expect(
      percent({
        step: "Transcribing",
        step_number: 1,
        steps: 2,
        fraction: 0.426,
        elapsed: 3,
      }),
    ).toBe(" 43%");
  });

  it("formats model option labels", () => {
    expect(
      formatModelOption({
        name: "large-v3",
        downloaded: true,
        default: true,
      }),
    ).toBe("large-v3 — most accurate, slower");
    expect(
      formatModelOption({
        name: "large-v3-turbo",
        downloaded: false,
        default: false,
        size: "1.6 GB",
      }),
    ).toBe(
      "large-v3-turbo — faster, needs about half the memory (downloads 1.6 GB on first use)",
    );
  });

  it("finds default model name", () => {
    expect(
      defaultModelName([
        { name: "large-v3", downloaded: true, default: false },
        { name: "large-v3-turbo", downloaded: true, default: true },
      ]),
    ).toBe("large-v3-turbo");
  });

  it("parses meeting id from hash", () => {
    expect(parseMeetingIdFromHash("")).toBeNull();
    expect(parseMeetingIdFromHash("#/meeting/2026-11-12-sync")).toBe(
      "2026-11-12-sync",
    );
    expect(parseMeetingIdFromHash("#/meeting/hello%20world")).toBe(
      "hello world",
    );
  });

  it("parses the meeting id and the line time from the hash", () => {
    expect(parseMeetingHash("")).toBeNull();
    expect(parseMeetingHash("#/meeting/a%3Fb")).toEqual({ id: "a?b", t: null });
    expect(parseMeetingHash("#/meeting/m-1?t=12.5")).toEqual({ id: "m-1", t: 12.5 });
    expect(parseMeetingHash("#/meeting/m-1?t=")).toEqual({ id: "m-1", t: null });
    expect(parseMeetingHash("#/meeting/m-1?t=abc")).toEqual({ id: "m-1", t: null });
    expect(parseMeetingIdFromHash("#/meeting/m-1?t=3")).toBe("m-1");
  });

  it("marks matched words case-insensitively, Thai included", () => {
    expect(markMatches("Let's start with the Budget.", "budget")).toEqual([
      { text: "Let's start with the ", match: false },
      { text: "Budget", match: true },
      { text: ".", match: false },
    ]);
    expect(markMatches("ได้ครับ งบประมาณปีนี้", "งบประมาณ")).toEqual([
      { text: "ได้ครับ ", match: false },
      { text: "งบประมาณ", match: true },
      { text: "ปีนี้", match: false },
    ]);
    expect(markMatches("a (b) a", "(b)")).toEqual([
      { text: "a ", match: false },
      { text: "(b)", match: true },
      { text: " a", match: false },
    ]);
    expect(markMatches("text", "  ")).toEqual([{ text: "text", match: false }]);
  });

  it("finds the segment nearest a time", () => {
    const segs = [{ start: 0 }, { start: 3 }, { start: 6 }];
    expect(nearestSegment(segs, 3.2)).toBe(1);
    expect(nearestSegment(segs, 100)).toBe(2);
    expect(nearestSegment([], 1)).toBe(-1);
  });
});

describe("groupTurns", () => {
  const seg = (start: number, end: number, speaker: string | null) => ({
    start,
    end,
    speaker,
    text: `${start}`,
  });
  const byTrack = (s: { speaker?: string | null }) =>
    s.speaker === "You" ? "mic" : "system";
  const shape = (turns: ReturnType<typeof groupTurns>) =>
    turns.map((t) => [t.speaker, t.lines.map((l) => l.index)]);

  it("merges consecutive lines of one speaker", () => {
    expect(
      shape(groupTurns([seg(0, 2, "A"), seg(2.5, 4, "A"), seg(4, 6, "B"), seg(6, 8, "A")], byTrack)),
    ).toEqual([["A", [0, 1]], ["B", [2]], ["A", [3]]]);
  });

  it("splits when the track changes even if the label repeats", () => {
    const track = (s: { start: number }) => (s.start < 2 ? "mic" : "system");
    expect(shape(groupTurns([seg(0, 1, "A"), seg(1, 3, "A"), seg(3, 4, "A")], track))).toEqual([
      ["A", [0, 1]],
      ["A", [2]],
    ]);
  });

  it("closes a turn after 60 s", () => {
    const lines = Array.from({ length: 8 }, (_, i) => seg(i * 10, i * 10 + 10, "A"));
    expect(shape(groupTurns(lines, byTrack))).toEqual([
      ["A", [0, 1, 2, 3, 4, 5]],
      ["A", [6, 7]],
    ]);
  });

  it("closes a turn at a pause over 2 s", () => {
    expect(shape(groupTurns([seg(0, 2, "A"), seg(4, 5, "A"), seg(7.5, 8, "A")], byTrack))).toEqual([
      ["A", [0, 1]],
      ["A", [2]],
    ]);
  });

  it("groups an unlabelled transcript on pauses only", () => {
    const t = groupTurns([seg(0, 2, null), seg(2, 4, null), seg(10, 12, null)], () => "mic");
    expect(shape(t)).toEqual([[null, [0, 1]], [null, [2]]]);
    expect(t[1].start).toBe(10);
  });
});
