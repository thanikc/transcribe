import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";

function mockJsonResponse(data: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(data),
  } as Response);
}

describe("App component", () => {
  beforeEach(() => {
    window.location.hash = "";
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders initial state, lists meetings, and opens a meeting transcript", async () => {
    const sampleMeeting = {
      id: "m-1",
      title: "Architecture Sync",
      started_at: "2026-11-12T10:00:00",
      duration: 125,
      mode: "mic+system",
      language: "auto",
      model: "large-v3",
      status: "transcribed",
      tracks: ["mic", "system"],
      audio_bytes: 1048576,
      progress: null,
      speaker_names: { A: "Alice" },
      detected_languages: { mic: "en", system: "th" },
    };

    const sampleDetail = {
      meeting: sampleMeeting,
      notes: "Action item: migrate to React",
      segments: [
        { start: 0, end: 2, speaker: "You", text: "Let us begin the review." },
        { start: 3, end: 6, speaker: "A", text: "สวัสดีค่ะ เห็นด้วยเลย" },
      ],
      transcript: "[00:00] You: Let us begin the review.\n[00:03] Alice: สวัสดีค่ะ เห็นด้วยเลย",
    };

    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/api/status")) {
        return mockJsonResponse({ recording: false });
      }
      if (url.endsWith("/api/meetings")) {
        return mockJsonResponse({ meetings: [sampleMeeting] });
      }
      if (url.endsWith("/api/models")) {
        return mockJsonResponse({
          models: [
            { name: "large-v3", downloaded: true, default: true },
            { name: "large-v3-turbo", downloaded: false, default: false, size: "1.6 GB" },
          ],
        });
      }
      if (url.endsWith("/api/sources")) {
        return mockJsonResponse({
          sources: {
            mic: { chosen: null, devices: [{ id: "mic-1", name: "USB Mic", default: true }] },
            system: { chosen: null, devices: [{ id: "sys-1", name: "Speakers", default: true }] },
          },
        });
      }
      if (url.endsWith("/api/version")) {
        return mockJsonResponse({ version: "1.0.0", update: null, checked: true });
      }
      if (url.endsWith("/api/meetings/m-1")) {
        return mockJsonResponse(sampleDetail);
      }
      return mockJsonResponse({ error: "not found" }, 404);
    });

    render(<App />);

    expect(screen.getByRole("status")).toHaveTextContent("Not recording");
    expect(
      await screen.findByText("Select a meeting to see its transcript."),
    ).toBeInTheDocument();

    // Wait for meetings list and version to load
    await waitFor(() => {
      expect(screen.getByText("Architecture Sync")).toBeInTheDocument();
    });
    expect(screen.getByText(/Transcribe 1\.0\.0 · Up to date/)).toBeInTheDocument();

    // Click the meeting in the sidebar
    await userEvent.click(screen.getByText("Architecture Sync"));

    // Verify transcript segments, speaker rename mapping, and notes render
    await waitFor(() => {
      expect(screen.getByText("Let us begin the review.")).toBeInTheDocument();
    });
    expect(screen.getByText("สวัสดีค่ะ เห็นด้วยเลย")).toBeInTheDocument();
    expect(screen.getByText("Action item: migrate to React")).toBeInTheDocument();

    // Speaker filter pills should appear when > 1 speaker
    const filterGroup = screen.getByRole("group", { name: "Filter by speaker" });
    expect(filterGroup).toBeInTheDocument();

    // Filter by Alice
    const aliceFilterBtn = screen.getAllByRole("button", { name: "Alice" })[0];
    await userEvent.click(aliceFilterBtn);
    const items = screen.getAllByRole("listitem", { hidden: true });
    const transcriptItems = items.filter((li) => li.hasAttribute("data-track"));
    expect(transcriptItems[0]).toHaveAttribute("hidden");
    expect(transcriptItems[1]).not.toHaveAttribute("hidden");
  });

  it("starts and stops a recording from the top dock", async () => {
    let isRecording = false;
    const recordedMeeting = {
      id: "m-rec",
      title: "Sprint Planning",
      started_at: "2026-11-12T12:00:00",
      duration: 10,
      mode: "mic",
      language: "en",
      model: "large-v3",
      status: "transcribed",
      tracks: ["mic"],
      audio_bytes: 4096,
      progress: null,
    };

    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      const method = init?.method || "GET";
      if (url.endsWith("/api/status")) {
        return mockJsonResponse(
          isRecording
            ? { recording: true, meeting_id: "m-rec", title: "Sprint Planning", elapsed: 4 }
            : { recording: false },
        );
      }
      if (url.endsWith("/api/recordings/start") && method === "POST") {
        isRecording = true;
        return mockJsonResponse(
          { meeting: { ...recordedMeeting, status: "recording" } },
          201,
        );
      }
      if (url.endsWith("/api/recordings/stop") && method === "POST") {
        isRecording = false;
        return mockJsonResponse({ meeting: recordedMeeting });
      }
      if (url.endsWith("/api/meetings")) {
        return mockJsonResponse({ meetings: isRecording ? [] : [recordedMeeting] });
      }
      if (url.endsWith("/api/meetings/m-rec")) {
        return mockJsonResponse({
          meeting: recordedMeeting,
          notes: null,
          segments: [{ start: 0, end: 2, speaker: null, text: "Sprint goals." }],
          transcript: "[00:00] Sprint goals.",
        });
      }
      if (url.endsWith("/api/models")) {
        return mockJsonResponse({
          models: [{ name: "large-v3", downloaded: true, default: true }],
        });
      }
      if (url.endsWith("/api/sources")) {
        return mockJsonResponse({
          sources: {
            mic: { chosen: null, devices: [] },
            system: { chosen: null, devices: [] },
          },
        });
      }
      if (url.endsWith("/api/version")) {
        return mockJsonResponse({ version: "dev", update: null });
      }
      return mockJsonResponse({});
    });

    render(<App />);

    const titleInput = screen.getByPlaceholderText("Meeting title…");
    await userEvent.type(titleInput, "Sprint Planning");

    const toggleBtn = screen.getByRole("button", { name: "Start recording" });
    await userEvent.click(toggleBtn);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Stop recording" }),
      ).toBeInTheDocument();
    });
    expect(screen.getByRole("status")).toHaveTextContent(/Recording.*Sprint Planning/);

    await userEvent.click(screen.getByRole("button", { name: "Stop recording" }));

    await waitFor(() => {
      expect(screen.getByText("Sprint goals.")).toBeInTheDocument();
    });
  });
});
