import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { fakeServer, jsonResponse, meeting } from "./fakeServer";

describe("mode switch beside the record button", () => {
  beforeEach(() => {
    window.location.hash = "";
    localStorage.clear();
  });
  afterEach(() => vi.restoreAllMocks());

  it("starts with the chosen mode and remembers it", async () => {
    const { calls } = fakeServer({
      route: (url, method) =>
        url.endsWith("/api/recordings/start") && method === "POST"
          ? jsonResponse({ meeting: meeting({ status: "recording", mode: "mic+system" }) }, 201)
          : undefined,
    });
    render(<App />);
    expect(screen.getByRole("radiogroup", { name: "Mode" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "In person" })).toBeChecked();
    await userEvent.click(screen.getByRole("radio", { name: "Online call" }));
    expect(localStorage.getItem("transcribe.mode")).toBe("mic+system");
    await userEvent.click(screen.getByRole("button", { name: "Start recording" }));
    await waitFor(() =>
      expect(calls.find((c) => c.url.endsWith("/start"))?.body).toMatchObject({
        mode: "mic+system",
      }),
    );
  });

  it("restores the last mode on page load", () => {
    localStorage.setItem("transcribe.mode", "mic+system");
    fakeServer();
    render(<App />);
    expect(screen.getByRole("radio", { name: "Online call" })).toBeChecked();
  });

  it("is disabled while recording and shows the mode being recorded", async () => {
    fakeServer({
      route: (url) =>
        url.endsWith("/api/status")
          ? jsonResponse({ recording: true, meeting_id: "m-1", title: "Call", mode: "mic+system", elapsed: 3 })
          : undefined,
    });
    render(<App />);
    await screen.findByRole("button", { name: "Stop recording" });
    const online = screen.getByRole("radio", { name: "Online call" });
    await waitFor(() => expect(online).toBeChecked());
    expect(online).toBeDisabled();
    expect(screen.getByRole("radio", { name: "In person" })).toBeDisabled();
  });

  it("settings no longer hold the mode", () => {
    fakeServer();
    render(<App />);
    expect(document.querySelector("#mode")).toBeNull();
    expect(screen.getByText("System audio from (online calls)")).toBeInTheDocument();
  });
});
