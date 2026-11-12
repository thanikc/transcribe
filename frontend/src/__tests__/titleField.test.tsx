import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { fakeServer, jsonResponse, meeting } from "./fakeServer";

function recordingServer() {
  let recording = false;
  let liveTitle = "";
  const server = fakeServer({
    route: (url, method, body) => {
      if (url.endsWith("/api/status"))
        return jsonResponse(
          recording
            ? { recording: true, meeting_id: "m-rec", title: liveTitle, mode: "mic", elapsed: 1 }
            : { recording: false },
        );
      if (url.endsWith("/api/recordings/start")) {
        recording = true;
        liveTitle = String(body!.title);
        return jsonResponse({ meeting: meeting({ id: "m-rec", title: liveTitle, status: "recording" }) }, 201);
      }
      if (url.endsWith("/api/recordings/stop")) {
        recording = false;
        return jsonResponse({ meeting: meeting({ id: "m-rec", title: liveTitle, status: "transcribing" }) });
      }
      if (url.endsWith("/api/meetings/m-rec/title") && method === "POST") {
        liveTitle = String(body!.title);
        return jsonResponse({ meeting: meeting({ id: "m-rec", title: liveTitle, status: "recording" }), notes: null, segments: null, transcript: null });
      }
      return undefined;
    },
  });
  return server;
}

describe("title field", () => {
  beforeEach(() => {
    window.location.hash = "";
    localStorage.clear();
  });
  afterEach(() => vi.restoreAllMocks());

  it("holds the live title while recording and is emptied after stop", async () => {
    recordingServer();
    render(<App />);
    const field = screen.getByPlaceholderText("Meeting title…");
    await userEvent.type(field, "Design review");
    await userEvent.click(screen.getByRole("button", { name: "Start recording" }));
    await screen.findByRole("button", { name: "Stop recording" });
    expect(field).toHaveValue("Design review");
    await userEvent.click(screen.getByRole("button", { name: "Stop recording" }));
    await screen.findByRole("button", { name: "Start recording" });
    expect(field).toHaveValue("");
  });

  it("renames the live recording on Enter", async () => {
    const { calls } = recordingServer();
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Start recording" }));
    await screen.findByRole("button", { name: "Stop recording" });
    const field = screen.getByPlaceholderText("Meeting title…");
    await userEvent.type(field, "Customer call{Enter}");
    await waitFor(() =>
      expect(calls.find((c) => c.url.endsWith("/m-rec/title"))?.body).toEqual({
        title: "Customer call",
      }),
    );
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("Customer call"),
    );
  });

  it("Escape restores the live title", async () => {
    const { calls } = recordingServer();
    render(<App />);
    const field = screen.getByPlaceholderText("Meeting title…");
    await userEvent.type(field, "Standup");
    await userEvent.click(screen.getByRole("button", { name: "Start recording" }));
    await screen.findByRole("button", { name: "Stop recording" });
    await userEvent.type(field, " typo{Escape}");
    expect(field).toHaveValue("Standup");
    await userEvent.tab();
    expect(calls.some((c) => c.url.endsWith("/title"))).toBe(false);
  });
});

describe("import title", () => {
  beforeEach(() => {
    window.location.hash = "";
  });
  afterEach(() => vi.restoreAllMocks());

  function importServer() {
    return fakeServer({
      route: (url) =>
        url.includes("/api/meetings/import")
          ? jsonResponse({ meeting: meeting({ id: "imp", status: "transcribing" }) }, 201)
          : undefined,
    });
  }

  it("uses its own title, not the recording title", async () => {
    const { calls } = importServer();
    render(<App />);
    await userEvent.type(screen.getByPlaceholderText("Meeting title…"), "Not this");
    await userEvent.upload(
      screen.getByLabelText("Import audio file"),
      new File(["x"], "standup.m4a", { type: "audio/mp4" }),
    );
    await userEvent.type(screen.getByLabelText("Title", { selector: "#import-title" }), "Standup");
    await userEvent.click(screen.getByRole("button", { name: "Import" }));
    await waitFor(() => {
      const url = calls.find((c) => c.url.includes("/import"))!.url;
      expect(new URL(url, "http://x").searchParams.get("title")).toBe("Standup");
    });
  });

  it("an empty title uses the file name, shown as the placeholder", async () => {
    const { calls } = importServer();
    render(<App />);
    await userEvent.upload(
      screen.getByLabelText("Import audio file"),
      new File(["x"], "standup.m4a", { type: "audio/mp4" }),
    );
    expect(screen.getByLabelText("Title", { selector: "#import-title" })).toHaveAttribute(
      "placeholder",
      "standup",
    );
    expect(
      screen.getByText("Transcribed as Auto · large-v3. Change these in Settings."),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Import" }));
    await waitFor(() => {
      const url = calls.find((c) => c.url.includes("/import"))!.url;
      expect(new URL(url, "http://x").searchParams.get("title")).toBe("standup");
    });
  });
});
