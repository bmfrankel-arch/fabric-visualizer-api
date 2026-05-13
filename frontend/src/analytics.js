/**
 * Lightweight usage analytics.
 *
 * Fires fire-and-forget POSTs to /api/analytics/event on the same backend
 * the rest of the app talks to. Reuses the X-API-Key header so brand-mode
 * portals authenticate cleanly; in internal Basic Auth mode the browser
 * sends the cached credentials automatically.
 *
 * Failures are silent so analytics never break the app.
 */

const API = (import.meta.env.VITE_BACKEND_URL || "").replace(/\/$/, "");
const API_KEY = import.meta.env.VITE_API_KEY || "";
const SESSION_KEY = "fv_session_id";

function getSessionId() {
  if (typeof window === "undefined") return "";
  try {
    let id = localStorage.getItem(SESSION_KEY);
    if (!id) {
      id =
        (crypto.randomUUID && crypto.randomUUID()) ||
        Math.random().toString(36).slice(2) + Date.now().toString(36);
      localStorage.setItem(SESSION_KEY, id);
    }
    return id;
  } catch {
    return "";
  }
}

export function track(event, { brand = null, ...payload } = {}) {
  if (typeof window === "undefined") return;
  const body = JSON.stringify({
    event,
    brand: brand || null,
    session_id: getSessionId(),
    payload,
  });
  const headers = { "Content-Type": "application/json" };
  if (API_KEY) headers["X-API-Key"] = API_KEY;
  try {
    fetch(`${API}/api/analytics/event`, {
      method: "POST",
      headers,
      body,
      keepalive: true,
      credentials: "include",
    }).catch(() => {});
  } catch {
    /* noop */
  }
}
