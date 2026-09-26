// Backend client. Token + port arrive via Electron IPC only (C2).
// Browser-dev fallback: ?port=&token= query params (local testing).

let backend = null; // { port, token }

export async function initBackend() {
  if (backend) return backend;
  if (window.jotva?.getBackend) {
    backend = await window.jotva.getBackend();
  } else {
    const params = new URLSearchParams(window.location.search);
    const port = params.get("port");
    const token = params.get("token");
    if (port && token) backend = { port: Number(port), token };
  }
  return backend;
}

function base() {
  if (!backend) throw new Error("Backend not initialized");
  return `http://127.0.0.1:${backend.port}`;
}

async function request(method, path, body) {
  const resp = await fetch(`${base()}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Jotva-Token": backend.token,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = null;
  try {
    data = await resp.json();
  } catch {
    data = null;
  }
  if (!resp.ok) {
    const detail = data?.detail || `Request failed (${resp.status})`;
    // Structured details (e.g. 402 pro_required / ai_limit) carry a code for the UI.
    const err = new Error(typeof detail === "object" ? detail.message || `Request failed (${resp.status})` : detail);
    err.status = resp.status;
    if (typeof detail === "object") {
      err.code = detail.code;
      err.feature = detail.feature;
    }
    throw err;
  }
  return data;
}

export const api = {
  get: (path) => request("GET", path),
  post: (path, body) => request("POST", path, body),
  patch: (path, body) => request("PATCH", path, body),
  delete: (path) => request("DELETE", path),
};

// URL for media elements (<audio src>), which cannot send auth headers —
// the backend accepts ?token= for this case.
export function mediaUrl(path) {
  if (!backend) return null;
  return `${base()}${path}?token=${encodeURIComponent(backend.token)}`;
}

export function connectWebSocket(onEvent) {
  if (!backend) return () => {};
  let ws;
  let closed = false;
  let pingTimer;
  let reconnectTimer;

  function open() {
    if (closed) return; // a pending reconnect fired after cleanup — stay closed
    ws = new WebSocket(
      `ws://127.0.0.1:${backend.port}/ws?token=${encodeURIComponent(backend.token)}`
    );
    ws.onmessage = (msg) => {
      try {
        const { event, data } = JSON.parse(msg.data);
        onEvent(event, data);
      } catch {
        /* ignore malformed frames */
      }
    };
    ws.onopen = () => {
      if (closed) {
        ws.close();
        return;
      }
      pingTimer = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send("ping");
      }, 25000);
    };
    ws.onclose = () => {
      clearInterval(pingTimer);
      if (!closed) reconnectTimer = setTimeout(open, 2000);
    };
  }
  open();
  return () => {
    closed = true;
    clearInterval(pingTimer);
    clearTimeout(reconnectTimer);
    ws?.close();
  };
}

export function openExternal(url) {
  if (window.jotva?.openExternal) return window.jotva.openExternal(url);
  window.open(url, "_blank", "noopener,noreferrer");
  return Promise.resolve({ ok: true });
}

export function showInFolder(path) {
  if (window.jotva?.showInFolder) return window.jotva.showInFolder(path);
  return Promise.resolve({ ok: false, error: "Not available in browser" });
}
