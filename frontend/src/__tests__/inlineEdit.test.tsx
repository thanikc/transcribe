import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import type { MeetingDetail } from "../types";
import { fakeServer, jsonResponse, meeting } from "./fakeServer";

function setup(failWith?: string) {
  let detail: MeetingDetail = {
    meeting: meeting({ title: "Weekly sync", speaker_names: {} }),
    notes: null,
    transcript: "",
    segments: [
      { start: 0, end: 1, speaker: "Speaker 1", text: "hello" },
      { start: 2, end: 3, speaker: "Speaker 2", text: "hi" },
    ],
  };
  const server = fakeServer({
    meetings: [detail.meeting],
    details: { "m-1": detail },
    route: (url, method, body) => {
      if (method !== "POST" && method !== "DELETE") return undefined;
      if (failWith) return jsonResponse({ error: failWith }, 400);
      if (url.endsWith("/title")) {
        detail = { ...detail, meeting: { ...detail.meeting, title: String(body!.title) } };
        return jsonResponse(detail);
      }
      if (url.endsWith("/speakers")) {
        const names = { ...detail.meeting.speaker_names };
        if (body!.name) names[String(body!.speaker)] = String(body!.name);
        else delete names[String(body!.speaker)];
        detail = { ...detail, meeting: { ...detail.meeting, speaker_names: names } };
        return jsonResponse(detail);
      }
      if (method === "DELETE") return jsonResponse({ deleted: "m-1" });
      return undefined;
    },
  });
  window.location.hash = "#/meeting/m-1";
  render(<App />);
  const posts = () => server.calls.filter((c) => c.method !== "GET");
  return { posts };
}

describe("inline rename and delete", () => {
  beforeEach(() => {
    window.location.hash = "";
  });
  afterEach(() => vi.restoreAllMocks());

  it("renames the meeting in place with Enter", async () => {
    const { posts } = setup();
    await userEvent.click(await screen.findByRole("button", { name: "Weekly sync" }));
    const input = screen.getByRole("textbox", { name: "Meeting title" });
    expect(input).toHaveValue("Weekly sync");
    await userEvent.clear(input);
    await userEvent.type(input, "Budget review{Enter}");
    expect(await screen.findByRole("button", { name: "Budget review" })).toBeInTheDocument();
    expect(posts()).toEqual([
      expect.objectContaining({ body: { title: "Budget review" } }),
    ]);
  });

  it("Escape cancels a title edit without saving", async () => {
    const { posts } = setup();
    await userEvent.click(await screen.findByRole("button", { name: "Weekly sync" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Meeting title" }), "x{Escape}");
    expect(screen.queryByRole("textbox", { name: "Meeting title" })).toBeNull();
    expect(screen.getByRole("button", { name: "Weekly sync" })).toBeInTheDocument();
    expect(posts()).toEqual([]);
  });

  it("a refused title keeps the editor open with the error", async () => {
    setup("title is too long");
    await userEvent.click(await screen.findByRole("button", { name: "Weekly sync" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Meeting title" }), "!{Enter}");
    expect(await screen.findByText("title is too long")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Meeting title" })).toHaveValue("Weekly sync!");
  });

  it("names a speaker from a popover, then resets it", async () => {
    const { posts } = setup();
    await screen.findByText("hello");
    const label = screen.getAllByRole("button", { name: "Speaker 1" }).find((b) => b.classList.contains("spk"))!;
    await userEvent.click(label);
    await userEvent.type(screen.getByRole("textbox", { name: "Name for Speaker 1" }), "Somchai{Enter}");
    const named = await screen.findAllByRole("button", { name: "Somchai" });
    const spk = named.find((b) => b.classList.contains("spk"))!;
    await userEvent.click(spk);
    expect(screen.getByRole("textbox", { name: "Name for Speaker 1" })).toHaveValue("Somchai");
    await userEvent.click(screen.getByRole("button", { name: "Reset to Speaker 1" }));
    await waitFor(() => expect(screen.queryAllByRole("button", { name: "Somchai" })).toHaveLength(0));
    expect(posts().map((c) => c.body)).toEqual([
      { speaker: "Speaker 1", name: "Somchai" },
      { speaker: "Speaker 1", name: "" },
    ]);
  });

  it("Escape closes the speaker popover without saving", async () => {
    const { posts } = setup();
    await screen.findByText("hello");
    const label = screen.getAllByRole("button", { name: "Speaker 2" }).find((b) => b.classList.contains("spk"))!;
    await userEvent.click(label);
    await userEvent.type(screen.getByRole("textbox", { name: "Name for Speaker 2" }), "Nok{Escape}");
    expect(screen.queryByRole("textbox", { name: "Name for Speaker 2" })).toBeNull();
    expect(posts()).toEqual([]);
  });

  it("delete asks in the page, naming the meeting, and Cancel keeps it", async () => {
    const { posts } = setup();
    await userEvent.click(await screen.findByText("Actions"));
    await userEvent.click(screen.getByRole("button", { name: "Delete meeting" }));
    expect(
      screen.getByText('Delete "Weekly sync"? Audio and transcript are removed for good.'),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
    expect(screen.getByText("Actions").closest("details")!.open).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Delete meeting" })).toBeInTheDocument();
    expect(posts()).toEqual([]);
  });

  it("delete goes ahead only after confirming", async () => {
    const { posts } = setup();
    await userEvent.click(await screen.findByText("Actions"));
    await userEvent.click(screen.getByRole("button", { name: "Delete meeting" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(window.location.hash).toBe(""));
    expect(posts()).toEqual([expect.objectContaining({ method: "DELETE" })]);
  });
});
