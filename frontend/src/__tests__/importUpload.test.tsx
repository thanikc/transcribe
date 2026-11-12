import { act, createEvent, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { fakeServer, fakeUploads, meeting } from "./fakeServer";

function drag(type: "dragEnter" | "dragOver" | "drop", files: File[]) {
  const ev = createEvent[type](window, {});
  Object.defineProperty(ev, "dataTransfer", {
    value: { types: ["Files"], files },
  });
  fireEvent(window, ev);
  return ev;
}

describe("import: drag and drop, upload progress", () => {
  beforeEach(() => {
    window.location.hash = "";
  });
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("dropping an audio file on the page offers to import it", async () => {
    fakeServer();
    render(<App />);
    const file = new File(["x"], "standup.m4a", { type: "audio/mp4" });
    act(() => {
      drag("dragEnter", [file]);
    });
    expect(screen.getByText("Drop to import")).toBeInTheDocument();
    let drop!: Event;
    act(() => {
      drop = drag("drop", [file]);
    });
    expect(drop.defaultPrevented).toBe(true);
    expect(screen.queryByText("Drop to import")).toBeNull();
    expect(document.getElementById("import-drawer")).toHaveProperty("open", true);
    expect(screen.getByText("Chosen: standup.m4a")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Import" })).toBeEnabled();
  });

  it("refuses a file that is neither audio nor video", () => {
    fakeServer();
    render(<App />);
    act(() => {
      drag("drop", [new File(["x"], "notes.txt", { type: "text/plain" })]);
    });
    expect(screen.getByText("notes.txt is not an audio or video file.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Import" })).toBeDisabled();
  });

  it("shows upload progress, then Converting…, and opens the meeting", async () => {
    fakeServer({ meetings: [meeting({ id: "imp" })] });
    const uploads = fakeUploads();
    render(<App />);
    await userEvent.click(screen.getByText("Import audio"));
    await userEvent.upload(
      screen.getByLabelText("Import audio file"),
      new File(["x"], "standup.m4a", { type: "audio/mp4" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Import" }));
    await waitFor(() => expect(uploads).toHaveLength(1));
    expect(uploads[0].headers["Content-Type"]).toBe("application/octet-stream");
    act(() => uploads[0].progress(43, 100));
    expect(screen.getByText("Uploading 43%")).toBeInTheDocument();

    // can't be dismissed mid-import
    fireEvent.keyDown(document, { key: "Escape" });
    expect(document.getElementById("import-drawer")).toHaveProperty("open", true);

    act(() => uploads[0].progress(100, 100));
    expect(screen.getByText("Converting…")).toBeInTheDocument();
    act(() => uploads[0].respond(201, { meeting: { id: "imp" } }));
    await waitFor(() => expect(window.location.hash).toBe("#/meeting/imp"));
  });

  it("shows the server's reason when the import is refused", async () => {
    fakeServer();
    const uploads = fakeUploads();
    render(<App />);
    await userEvent.upload(
      screen.getByLabelText("Import audio file"),
      new File(["x"], "broken.mp3", { type: "audio/mpeg" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Import" }));
    await waitFor(() => expect(uploads).toHaveLength(1));
    act(() => uploads[0].respond(400, { error: "could not read the file as audio" }));
    expect(await screen.findByText("could not read the file as audio")).toBeInTheDocument();
  });

  it("says when the service can't be reached", async () => {
    fakeServer();
    const uploads = fakeUploads();
    render(<App />);
    await userEvent.upload(
      screen.getByLabelText("Import audio file"),
      new File(["x"], "a.mp3", { type: "audio/mpeg" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Import" }));
    await waitFor(() => expect(uploads).toHaveLength(1));
    act(() => uploads[0].fail());
    expect(await screen.findByText("Cannot reach the recorder service.")).toBeInTheDocument();
  });
});
