import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { fakeServer, meeting } from "./fakeServer";

describe("recorder unreachable", () => {
  beforeEach(() => {
    window.location.hash = "";
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("says so after three failed status checks, disables Start, and recovers by itself", async () => {
    let down = true;
    const { calls } = fakeServer({
      meetings: [meeting({ title: "Back again" })],
      route: (url) => {
        if (down && url.endsWith("/api/status"))
          return Promise.reject(new TypeError("Failed to fetch"));
        return undefined;
      },
    });
    render(<App />);
    const start = screen.getByRole("button", { name: "Start recording" });

    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(screen.queryByText(/Can't reach the recorder/)).toBeNull();
    await act(() => vi.advanceTimersByTimeAsync(1000));

    expect(screen.getByText(/Can't reach the recorder/)).toHaveAttribute("role", "alert");
    expect(screen.getByRole("status")).toHaveTextContent("Disconnected");
    expect(start).toBeDisabled();

    down = false;
    const listLoadsBefore = calls.filter((c) => c.url.endsWith("/api/meetings")).length;
    await act(() => vi.advanceTimersByTimeAsync(1000));

    expect(screen.queryByText(/Can't reach the recorder/)).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("Not recording");
    expect(start).toBeEnabled();
    expect(
      calls.filter((c) => c.url.endsWith("/api/meetings")).length,
    ).toBeGreaterThan(listLoadsBefore);
    expect(calls.filter((c) => c.url.endsWith("/api/models")).length).toBe(2);
  });
});
