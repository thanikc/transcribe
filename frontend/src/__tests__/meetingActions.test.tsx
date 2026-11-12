import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import type { MeetingStatus } from "../types";
import { fakeServer, meeting } from "./fakeServer";

function openMeetingWithStatus(status: MeetingStatus) {
  const m = meeting({ status, error: status === "failed" ? "boom" : null });
  fakeServer({
    meetings: [m],
    details: {
      "m-1": {
        meeting: m,
        notes: null,
        transcript: "",
        segments: status === "transcribed"
          ? [{ start: 0, end: 1, speaker: null, text: "hello" }]
          : null,
      },
    },
  });
  window.location.hash = "#/meeting/m-1";
  render(<App />);
}

describe("meeting actions in the header", () => {
  beforeEach(() => {
    window.location.hash = "";
  });
  afterEach(() => vi.restoreAllMocks());

  it.each(["transcribed", "failed", "transcribing"] as const)(
    "a %s meeting has an Actions menu in its header",
    async (status) => {
      openMeetingWithStatus(status);
      await screen.findByRole("button", { name: "Weekly sync" });
      const summary = screen.getByText("Actions");
      expect(summary.closest(".meeting-header")).not.toBeNull();
      expect(document.querySelector(".secondary-drawer")).toBeNull();
    },
  );

  it("a recording meeting has no Actions menu", async () => {
    openMeetingWithStatus("recording");
    await screen.findByText(/Recording in progress/);
    expect(screen.queryByText("Actions")).toBeNull();
  });

  it("delete is offered for finished meetings but not while transcribing", async () => {
    openMeetingWithStatus("transcribing");
    await screen.findByText("Actions");
    expect(screen.queryByRole("button", { name: "Delete meeting", hidden: true })).toBeNull();
    expect(screen.getByRole("button", { name: "Transcribe again", hidden: true })).toBeDisabled();
  });

  it("a failed meeting's Transcribe again… button opens the Actions menu", async () => {
    openMeetingWithStatus("failed");
    const open = await screen.findByRole("button", { name: "Transcribe again…" });
    const details = screen.getByText("Actions").closest("details")!;
    expect(details.open).toBe(false);
    await userEvent.click(open);
    expect(details.open).toBe(true);
    expect(screen.getByLabelText("Language", { selector: "#again-language" })).toHaveFocus();
  });
});
