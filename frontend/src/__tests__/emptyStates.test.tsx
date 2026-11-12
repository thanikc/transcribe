import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { fakeServer, meeting } from "./fakeServer";

describe("empty and loading states", () => {
  beforeEach(() => {
    window.location.hash = "";
  });
  afterEach(() => vi.restoreAllMocks());

  it("with no meetings, says how to make one", async () => {
    fakeServer({ meetings: [] });
    render(<App />);
    expect(
      await screen.findByText(
        "No meetings yet. Press Start recording, or use Import audio to transcribe a file you already have.",
      ),
    ).toBeInTheDocument();
  });

  it("with meetings, asks to pick one", async () => {
    fakeServer({ meetings: [meeting()] });
    render(<App />);
    expect(
      await screen.findByText("Select a meeting to see its transcript."),
    ).toBeInTheDocument();
  });

  it("shows Loading… while a meeting is being fetched", async () => {
    fakeServer({
      meetings: [meeting()],
      route: (url) =>
        url.endsWith("/api/meetings/m-1") ? new Promise(() => {}) : undefined,
    });
    window.location.hash = "#/meeting/m-1";
    render(<App />);
    expect(await screen.findByText("Loading…")).toHaveClass("loading");
  });
});
