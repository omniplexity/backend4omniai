import { apiBaseUrl } from "./config.js";
import { getCsrfToken } from "./auth.js";

async function normalizeResponse(res) {
  if (res.ok) {
    return res.json().catch(() => null);
  }
  const payload = await res.json().catch(() => null);
  if (payload?.error) {
    const error = new Error(payload.error.message);
    error.code = payload.error.code;
    error.requestId = payload.error.request_id;
    throw error;
  }
  throw new Error("Unexpected error");
}

function buildUrl(path, params) {
  const url = new URL(`${apiBaseUrl()}${path}`);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value != null) {
        url.searchParams.set(key, String(value));
      }
    });
  }
  return url.toString();
}

export async function get(path, params) {
  const res = await fetch(buildUrl(path, params), {
    credentials: "include",
  });
  return normalizeResponse(res);
}

export async function post(path, body, requiresCsrf = true) {
  return sendWithBody("POST", path, body, requiresCsrf);
}

export async function patch(path, body) {
  return sendWithBody("PATCH", path, body, true);
}

export async function del(path) {
  return sendWithBody("DELETE", path, null, true);
}

async function sendWithBody(method, path, body, csrf) {
  const headers = { "Content-Type": "application/json" };
  if (csrf) {
    headers["X-CSRF-Token"] = await getCsrfToken();
  }
  const res = await fetch(buildUrl(path), {
    method,
    credentials: "include",
    headers,
    body: body ? JSON.stringify(body) : null,
  });
  return normalizeResponse(res);
}

export async function getMe() {
  return get("/auth/me");
}

export async function getAdminUsers(params) {
  return get("/admin/users", params);
}

export async function patchAdminUser(userId, body) {
  return patch(`/admin/users/${userId}`, body);
}

export async function getAdminUsage(params) {
  return get("/admin/usage", params);
}

export async function getAdminAudit(params) {
  return get("/admin/audit", params);
}

export async function getAdminInvites() {
  return get("/admin/invites");
}

export async function postAdminInvite(body) {
  return post("/admin/invites", body);
}
