import { describe, expect, it } from "vitest";
import {
  defaultModelName,
  fileSize,
  formatModelOption,
  mmss,
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
});
