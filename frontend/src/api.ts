export async function api<T = unknown>(
  method: "GET" | "POST" | "DELETE",
  path: string,
  body?: Record<string, unknown>,
): Promise<T> {
  const opts: RequestInit = { method, headers: {} };
  if (method !== "GET") {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = JSON.stringify(body || {});
  }
  let res: Response;
  try {
    res = await fetch(path, opts);
  } catch {
    throw new Error("Cannot reach the recorder service.");
  }
  let data: { error?: string } | null = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON */
  }
  if (!res.ok) {
    throw new Error(data?.error || `Request failed (${res.status})`);
  }
  return data as T;
}

export async function uploadAudioFile(
  file: File,
  params: { title: string; language: string; model: string },
): Promise<{ meeting: { id: string } }> {
  const search = new URLSearchParams(params);
  let res: Response;
  try {
    res = await fetch("/api/meetings/import?" + search.toString(), {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: file,
    });
  } catch {
    throw new Error("Cannot reach the recorder service.");
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(data?.error || `Import failed (${res.status})`);
  }
  return data;
}
