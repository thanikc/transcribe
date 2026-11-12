import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { fakeServer, meeting } from "./fakeServer";

describe("transcript as speaker turns", () => {
  beforeEach(() => {
    window.location.hash = "";
  });
  afterEach(() => vi.restoreAllMocks());

  async function open() {
    const m = meeting();
    fakeServer({
      meetings: [m],
      details: {
        "m-1": {
          meeting: m,
          notes: null,
          transcript: "",
          segments: [
            { start: 0, end: 2, speaker: "Speaker 1", text: "Good morning." },
            { start: 2.5, end: 4, speaker: "Speaker 1", text: "Shall we start?" },
            { start: 4.5, end: 6, speaker: "Speaker 2", text: "Yes, please." },
          ],
        },
      },
    });
    window.location.hash = "#/meeting/m-1";
    render(<App />);
    await screen.findByText("Good morning.");
  }

  it("shows consecutive lines of one speaker as one turn, naming the speaker once", async () => {
    await open();
    const turns = document.querySelectorAll("ol.transcript > li");
    expect(turns).toHaveLength(2);
    expect(turns[0]).toHaveTextContent("Good morning. Shall we start?");
    expect(turns[0].querySelectorAll("button.spk")).toHaveLength(1);
  });

  it("clicking a sentence plays from its start", async () => {
    const play = vi
      .spyOn(HTMLMediaElement.prototype, "play")
      .mockResolvedValue(undefined);
    await open();
    const audio = document.getElementById("audio-mic") as HTMLAudioElement;
    Object.defineProperty(audio, "readyState", { value: 4 });
    await userEvent.click(screen.getByText("Shall we start?"));
    expect(play).toHaveBeenCalled();
    expect(audio.currentTime).toBe(2.5);
  });

  it("filtering by speaker hides whole turns", async () => {
    await open();
    await userEvent.click(screen.getByRole("button", { name: "Speaker 2", pressed: false }));
    const turns = document.querySelectorAll("ol.transcript > li");
    expect(turns[0]).toHaveAttribute("hidden");
    expect(turns[1]).not.toHaveAttribute("hidden");
  });
});
