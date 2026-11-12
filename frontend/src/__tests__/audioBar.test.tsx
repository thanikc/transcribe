import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AudioBar, type AudioBarHandle } from "../components/AudioBar";
import { playingLine } from "../utils";

function fakeMedia() {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function (
    this: HTMLMediaElement,
  ) {
    Object.defineProperty(this, "paused", { value: false, configurable: true });
    this.dispatchEvent(new Event("play"));
    return Promise.resolve();
  });
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(function (
    this: HTMLMediaElement,
  ) {
    Object.defineProperty(this, "paused", { value: true, configurable: true });
    this.dispatchEvent(new Event("pause"));
  });
}

function loaded(a: HTMLAudioElement, duration = 120) {
  Object.defineProperty(a, "readyState", { value: 4, configurable: true });
  Object.defineProperty(a, "duration", { value: duration, configurable: true });
}

function setup(tracks = ["mic", "system"]) {
  const ref = createRef<AudioBarHandle>();
  const onTime = vi.fn();
  render(
    <AudioBar ref={ref} meetingId="m-1" tracks={tracks} duration={120} onTimeUpdate={onTime} />,
  );
  const mic = document.getElementById("audio-mic") as HTMLAudioElement;
  const sys = document.getElementById("audio-system") as HTMLAudioElement | null;
  loaded(mic);
  if (sys) loaded(sys);
  return { ref, onTime, mic, sys: sys! };
}

describe("one player for all tracks", () => {
  beforeEach(() => {
    localStorage.clear();
    fakeMedia();
  });
  afterEach(() => vi.restoreAllMocks());

  it("plays both tracks together from a moment", () => {
    const { ref, mic, sys } = setup();
    act(() => ref.current!.playFrom(42));
    expect(mic.currentTime).toBe(42);
    expect(sys.currentTime).toBe(42);
    expect(mic.paused).toBe(false);
    expect(sys.paused).toBe(false);
    expect(screen.getByRole("button", { name: "Pause" })).toBeInTheDocument();
  });

  it("pauses both, and skips both back and forward by 10 s", async () => {
    const { ref, mic, sys } = setup();
    act(() => ref.current!.playFrom(30));
    await userEvent.click(screen.getByRole("button", { name: "Pause" }));
    expect(mic.paused && sys.paused).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Back 10 seconds" }));
    expect([mic.currentTime, sys.currentTime]).toEqual([20, 20]);
    await userEvent.click(screen.getByRole("button", { name: "Forward 10 seconds" }));
    expect([mic.currentTime, sys.currentTime]).toEqual([30, 30]);
  });

  it("re-seeks a follower that drifts more than 0.2 s", () => {
    const { ref, mic, sys } = setup();
    act(() => ref.current!.playFrom(10));
    sys.currentTime = 10.1;
    mic.currentTime = 10.2;
    fireEvent.timeUpdate(mic);
    expect(sys.currentTime).toBe(10.1);
    mic.currentTime = 11;
    fireEvent.timeUpdate(mic);
    expect(sys.currentTime).toBe(11);
  });

  it("leaves a follower that has ended paused", () => {
    const { ref, mic, sys } = setup();
    loaded(sys, 60);
    act(() => ref.current!.playFrom(10));
    sys.pause();
    Object.defineProperty(sys, "ended", { value: true, configurable: true });
    mic.currentTime = 65;
    fireEvent.timeUpdate(mic);
    expect(sys.paused).toBe(true);
    expect(sys.currentTime).not.toBe(65);
  });

  it("remembers the speed and applies it to every track", async () => {
    const first = setup();
    await userEvent.selectOptions(screen.getByLabelText("Speed"), "1.5");
    expect(first.mic.playbackRate).toBe(1.5);
    expect(first.sys.playbackRate).toBe(1.5);
    expect(localStorage.getItem("transcribe.playbackRate")).toBe("1.5");
    document.body.innerHTML = "";
    setup();
    expect(screen.getByLabelText("Speed")).toHaveValue("1.5");
  });

  it("mutes one track", async () => {
    const { mic, sys } = setup();
    await userEvent.click(screen.getByRole("button", { name: "Microphone" }));
    expect(mic.muted).toBe(true);
    expect(sys.muted).toBe(false);
  });

  it("has no mute toggles with one track", () => {
    setup(["mic"]);
    expect(screen.queryByRole("button", { name: "Microphone" })).toBeNull();
  });

  it("Space toggles play and arrows seek 5 s, but not while typing", () => {
    const { mic } = setup(["mic"]);
    mic.currentTime = 20;
    fireEvent.keyDown(document.body, { key: " " });
    expect(mic.paused).toBe(false);
    fireEvent.keyDown(document.body, { key: "ArrowLeft" });
    expect(mic.currentTime).toBe(15);
    fireEvent.keyDown(document.body, { key: "ArrowRight" });
    expect(mic.currentTime).toBe(20);
    const input = document.createElement("input");
    document.body.append(input);
    input.focus();
    fireEvent.keyDown(input, { key: " " });
    expect(mic.paused).toBe(false);
  });
});

describe("playingLine", () => {
  const segs = [
    { start: 0, end: 5, text: "a" },
    { start: 3, end: 8, text: "b" },
    { start: 9, end: 10, text: "c" },
  ];
  it("picks the line holding the time, the later-starting one when lines overlap", () => {
    expect(playingLine(segs, 1)).toBe(0);
    expect(playingLine(segs, 4)).toBe(1);
    expect(playingLine(segs, 8.5)).toBeNull();
    expect(playingLine(segs, null)).toBeNull();
  });
});
