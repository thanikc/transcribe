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

/** Uploads with XMLHttpRequest, since fetch can't report upload progress. */
export function uploadAudioFile(
  file: File,
  params: { title: string; language: string; model: string },
  onProgress?: (fraction: number) => void,
): Promise<{ meeting: { id: string } }> {
  const search = new URLSearchParams(params);
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/meetings/import?" + search.toString());
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && e.total > 0) onProgress?.(e.loaded / e.total);
    };
    // all bytes sent; the server converts the file before it answers
    xhr.upload.onload = () => onProgress?.(1);
    xhr.onload = () => {
      let data: { error?: string; meeting?: { id: string } } | null = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        /* non-JSON */
      }
      if (xhr.status >= 200 && xhr.status < 300 && data?.meeting) {
        resolve(data as { meeting: { id: string } });
      } else {
        reject(new Error(data?.error || `Import failed (${xhr.status})`));
      }
    };
    xhr.onerror = () => reject(new Error("Cannot reach the recorder service."));
    xhr.send(file);
  });
}
