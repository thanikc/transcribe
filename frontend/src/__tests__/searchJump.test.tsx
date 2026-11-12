import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { fakeServer, jsonResponse, meeting } from "./fakeServer";

describe("search hit opens the matching line", () => {
  beforeEach(() => {
    window.location.hash = "";
  });
  afterEach(() => vi.restoreAllMocks());

  function setup() {
    const m = meeting({ title: "Budget" });
    const segments = Array.from({ length: 12 }, (_, i) => ({
      start: i * 10,
      end: i * 10 + 5,
      speaker: i % 2 ? "Speaker 2" : "Speaker 1",
      text: i === 9 ? "Let's start with the budget." : `line ${i}`,
    }));
    fakeServer({
      meetings: [m],
      details: { "m-1": { meeting: m, notes: null, transcript: "", segments } },
      route: (url) =>
        url.includes("/api/search")
          ? jsonResponse({
              hits: [{ meeting_id: "m-1", title: "Budget", start: 90, timestamp: "[01:30]", speaker: "Speaker 2", text: "Let's start with the budget." }],
            })
          : undefined,
    });
    render(<App />);
  }

  it("marks the matched words and opens the meeting at that line, revealing it", async () => {
    setup();
    // open the meeting and hide the target: filter to the other speaker
    window.location.hash = "#/meeting/m-1";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    await screen.findByText("line 0");
    await userEvent.click(screen.getByRole("button", { name: "Speaker 1", pressed: false }));
    expect(screen.getByText("Let's start with the budget.", { selector: ".seg-text" }).closest("li")).toHaveAttribute("hidden");

    await userEvent.type(screen.getByPlaceholderText("Search words…"), "BUDGET{Enter}");
    const hit = await screen.findByRole("button", { name: /\[01:30\]/ });
    expect(hit.querySelector("mark")).toHaveTextContent("budget");

    await userEvent.click(hit);
    expect(window.location.hash).toBe("#/meeting/m-1?t=90");
    await waitFor(() => {
      const row = screen.getByText("Let's start with the budget.", { selector: ".seg-text" }).closest("li")!;
      expect(row).toHaveClass("focus");
      expect(row).not.toHaveAttribute("hidden");
    });
  });

  it("expands a collapsed transcript to show the hit, and scrolls again on a second click", async () => {
    setup();
    window.location.hash = "#/meeting/m-1";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    await screen.findByText("line 0");
    await userEvent.click(screen.getByRole("button", { name: "Collapse transcript" }));
    expect(screen.queryByText("Let's start with the budget.", { selector: ".seg-text" })).toBeNull();

    const scrolled = vi.fn();
    Element.prototype.scrollIntoView = scrolled;
    await userEvent.type(screen.getByPlaceholderText("Search words…"), "budget{Enter}");
    const hit = await screen.findByRole("button", { name: /\[01:30\]/ });
    await userEvent.click(hit);
    await waitFor(() =>
      expect(screen.getByText("Let's start with the budget.", { selector: ".seg-text" }).closest("li")).toHaveClass("focus"),
    );
    const first = scrolled.mock.calls.length;
    expect(first).toBeGreaterThan(0);
    await userEvent.click(hit);
    await waitFor(() => expect(scrolled.mock.calls.length).toBeGreaterThan(first));
    // @ts-expect-error jsdom has none
    delete Element.prototype.scrollIntoView;
  });
});
