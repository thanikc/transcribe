import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { speakerPalette } from "../utils";
import { fakeServer, meeting } from "./fakeServer";

describe("speakerPalette", () => {
  it("numbers speakers by first appearance and wraps after six", () => {
    const segs = ["B", "A", null, "B", "C", "D", "E", "F", "G"].map((sp, i) => ({
      start: i,
      end: i + 1,
      text: "x",
      speaker: sp,
    }));
    expect(speakerPalette(segs)).toEqual({
      B: 0, A: 1, C: 2, D: 3, E: 4, F: 5, G: 0,
    });
    expect(speakerPalette(null)).toEqual({});
  });
});

describe("speaker colours", () => {
  beforeEach(() => {
    window.location.hash = "";
  });
  afterEach(() => vi.restoreAllMocks());

  it("a speaker has the same colour whichever meeting was opened before", async () => {
    const a = meeting({ id: "a", title: "A" });
    const b = meeting({ id: "b", title: "B" });
    fakeServer({
      meetings: [a, b],
      details: {
        a: { meeting: a, notes: null, transcript: "", segments: [
          { start: 0, end: 1, speaker: "Speaker 1", text: "first in a" },
        ] },
        b: { meeting: b, notes: null, transcript: "", segments: [
          { start: 0, end: 1, speaker: "Speaker 7", text: "only in b" },
        ] },
      },
    });
    render(<App />);
    window.location.hash = "#/meeting/b";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    await screen.findByText("only in b");
    window.location.hash = "#/meeting/a";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    await screen.findByText("first in a");
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Speaker 1" }),
      ).toHaveStyle({ color: "var(--sp0)" }),
    );
  });
});
