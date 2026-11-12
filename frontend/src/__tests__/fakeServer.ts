import { vi } from "vitest";
import type { Meeting, MeetingDetail } from "../types";

export function jsonResponse(data: unknown, status = 200): Promise<Response> {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(data),
  } as Response);
}

export function meeting(over: Partial<Meeting> = {}): Meeting {
  return {
    id: "m-1",
    title: "Weekly sync",
    started_at: "2026-11-12T10:00:00",
    duration: 60,
    mode: "mic",
    language: "en",
    model: "large-v3",
    status: "transcribed",
    tracks: ["mic"],
    audio_bytes: 1024,
    progress: null,
    ...over,
  };
}

type Route = (
  url: string,
  method: string,
  body: Record<string, unknown> | undefined,
) => Promise<Response> | undefined;

/** Stubs fetch with the usual idle service; `route` answers first when it returns a response. */
export function fakeServer(opts: {
  meetings?: Meeting[];
  details?: Record<string, MeetingDetail>;
  route?: Route;
} = {}) {
  const calls: { url: string; method: string; body?: Record<string, unknown> }[] = [];
  const spy = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = String(input);
    const method = init?.method || "GET";
    const body =
      typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
    calls.push({ url, method, body });
    const custom = opts.route?.(url, method, body);
    if (custom) return custom;
    if (url.endsWith("/api/status")) return jsonResponse({ recording: false });
    if (url.endsWith("/api/meetings"))
      return jsonResponse({ meetings: opts.meetings || [] });
    if (url.endsWith("/api/models"))
      return jsonResponse({
        models: [{ name: "large-v3", downloaded: true, default: true }],
      });
    if (url.endsWith("/api/sources"))
      return jsonResponse({
        sources: {
          mic: { chosen: null, devices: [] },
          system: { chosen: null, devices: [] },
        },
      });
    if (url.endsWith("/api/version"))
      return jsonResponse({ version: "dev", update: null });
    const m = url.match(/\/api\/meetings\/([^/?]+)$/);
    if (m && method === "GET") {
      const d = opts.details?.[decodeURIComponent(m[1])];
      if (d) return jsonResponse(d);
    }
    return jsonResponse({ error: "not found" }, 404);
  });
  return { spy, calls };
}

/** Replaces XMLHttpRequest (used for uploads); each request waits for the test to answer it. */
export function fakeUploads() {
  const requests: FakeXhr[] = [];
  class FakeXhr {
    method = "";
    url = "";
    headers: Record<string, string> = {};
    body: unknown;
    status = 0;
    responseText = "";
    upload: {
      onprogress: ((e: { lengthComputable: boolean; loaded: number; total: number }) => void) | null;
      onload: (() => void) | null;
    } = { onprogress: null, onload: null };
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    open(method: string, url: string) {
      this.method = method;
      this.url = url;
    }
    setRequestHeader(k: string, v: string) {
      this.headers[k] = v;
    }
    send(body: unknown) {
      this.body = body;
      requests.push(this);
    }
    progress(loaded: number, total: number) {
      this.upload.onprogress?.({ lengthComputable: true, loaded, total });
      if (loaded >= total) this.upload.onload?.();
    }
    respond(status: number, data: unknown) {
      this.status = status;
      this.responseText = JSON.stringify(data);
      this.onload?.();
    }
    fail() {
      this.onerror?.();
    }
  }
  vi.stubGlobal("XMLHttpRequest", FakeXhr);
  return requests;
}
