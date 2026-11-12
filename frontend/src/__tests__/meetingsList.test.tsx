import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { groupByDay } from "../utils";
import { fakeServer, meeting } from "./fakeServer";

const at = (y: number, mo: number, d: number, h = 12, mi = 0) =>
  new Date(y, mo - 1, d, h, mi).toISOString();
const month = (y: number, mo: number) =>
  new Date(y, mo - 1, 1).toLocaleDateString(undefined, { month: "long", year: "numeric" });

describe("groupByDay", () => {
  // Thursday 12 November 2026, 00:30 local
  const now = new Date(2026, 10, 12, 0, 30);
  const labels = (starts: string[]) =>
    groupByDay(starts.map((started_at) => ({ started_at })), now).map((g) => [
      g.label,
      g.meetings.length,
    ]);

  it("splits at local midnight into Today and Yesterday", () => {
    expect(labels([at(2026, 11, 12, 0, 5), at(2026, 11, 11, 23, 55), at(2026, 11, 11, 0, 0)])).toEqual([
      ["Today", 1],
      ["Yesterday", 2],
    ]);
  });

  it("puts the rest of this week (from Monday) under Earlier this week, then months", () => {
    expect(
      labels([at(2026, 11, 10), at(2026, 11, 9, 8), at(2026, 11, 8), at(2026, 11, 1), at(2026, 10, 31), at(2025, 10, 2)]),
    ).toEqual([
      ["Earlier this week", 2],
      [month(2026, 11), 2],
      [month(2026, 10), 1],
      [month(2025, 10), 1],
    ]);
  });

  it("on a Monday, Sunday is Yesterday and nothing is earlier this week", () => {
    const monday = new Date(2026, 10, 9, 9);
    expect(
      groupByDay([{ started_at: at(2026, 11, 8) }, { started_at: at(2026, 11, 7) }], monday).map((g) => g.label),
    ).toEqual(["Yesterday", month(2026, 11)]);
  });
});

describe("meetings list", () => {
  beforeEach(() => {
    window.location.hash = "";
  });
  afterEach(() => vi.restoreAllMocks());

  it("shows a badge only for meetings that are not simply transcribed, under date headings", async () => {
    const today = new Date();
    fakeServer({
      meetings: [
        meeting({ id: "a", title: "Done", started_at: today.toISOString(), status: "transcribed" }),
        meeting({ id: "b", title: "Broke", started_at: today.toISOString(), status: "failed" }),
      ],
    });
    render(<App />);
    const done = await screen.findByText("Done");
    const group = screen.getByRole("region", { name: "Today" });
    expect(within(group).getByText("Broke")).toBeInTheDocument();
    expect(done.closest("button")!.querySelector(".badge")).toBeNull();
    expect(screen.getByText("Broke").closest("button")!.querySelector(".badge")).toHaveTextContent("failed");
    expect(done.closest("button")!.querySelector(".m")!.textContent).not.toMatch(/KB|MB|B$/);
  });
});
