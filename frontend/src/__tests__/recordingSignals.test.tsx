import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { fakeServer, jsonResponse } from "./fakeServer";

function setHidden(hidden: boolean) {
  Object.defineProperty(document, "hidden", { value: hidden, configurable: true });
}

describe("recording shown outside the page", () => {
  let status: Record<string, unknown>;
  beforeEach(() => {
    window.location.hash = "";
    vi.useFakeTimers({
      shouldAdvanceTime: true,
      toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "Date", "performance"],
    });
    status = { recording: true, meeting_id: "m-1", title: "Call", mode: "mic+system", elapsed: 1, levels: { mic: 0, system: 0.5 } };
  });
  afterEach(() => {
    setHidden(false);
    vi.useRealTimers();
    vi.restoreAllMocks();
    document.title = "Meetings";
  });

  function start() {
    const server = fakeServer({
      route: (url) => (url.endsWith("/api/status") ? jsonResponse(status) : undefined),
    });
    render(<App />);
    return server;
  }

  it("the tab title and icon say recording, and stop saying it after stop", async () => {
    start();
    await act(() => vi.advanceTimersByTimeAsync(10));
    expect(document.title).toBe("● Recording – Meetings");
    status = { recording: false };
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(document.title).toBe("Meetings");
  });

  it("a hidden tab checks every 5 s while recording, so the title corrects itself", async () => {
    const { calls } = start();
    await act(() => vi.advanceTimersByTimeAsync(10));
    setHidden(true);
    status = { recording: false };
    const polls = () => calls.filter((c) => c.url.endsWith("/api/status")).length;
    const before = polls();
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(polls()).toBe(before + 1); // the first hidden tick checks at once
    await act(() => vi.advanceTimersByTimeAsync(3000));
    expect(polls()).toBe(before + 1);
    expect(document.title).toBe("Meetings");
    await act(() => vi.advanceTimersByTimeAsync(10000));
    expect(polls()).toBe(before + 1); // not recording any more: a hidden tab asks nothing
  });

  it("a track silent for 10 s shows a warning naming it", async () => {
    start();
    // one status poll per second, as the page does
    const seconds = async (n: number) => {
      for (let i = 0; i < n; i++) await act(() => vi.advanceTimersByTimeAsync(1000));
    };
    await seconds(9);
    expect(screen.queryByText(/no sound/)).toBeNull();
    await seconds(3);
    const chip = screen.getByText("⚠ Microphone: no sound");
    expect(chip).toHaveAttribute("role", "status");
    expect(screen.queryByText("⚠ System audio: no sound")).toBeNull();
  });
});
