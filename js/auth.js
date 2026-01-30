import { apiBaseUrl } from "./config.js";

const authState = {
  csrfToken: null,
};

async function fetchCsrfToken() {
  const res = await fetch(`${apiBaseUrl()}/auth/csrf`, {
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error("Unable to refresh CSRF token");
  }
  const payload = await res.json();
  authState.csrfToken = payload.csrf_token;
  return authState.csrfToken;
}

export async function getCsrfToken() {
  if (authState.csrfToken) {
    return authState.csrfToken;
  }
  return fetchCsrfToken();
}

export async function login(credentials) {
  const res = await fetch(`${apiBaseUrl()}/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(credentials),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => null);
    if (payload?.error?.message) {
      const error = new Error(payload.error.message);
      error.code = payload.error.code;
      error.requestId = payload.error.request_id;
      throw error;
    }
    throw new Error("Invalid credentials");
  }
  await fetchCsrfToken();
  return res.json();
}

export async function logout() {
  const token = await getCsrfToken();
  await fetch(`${apiBaseUrl()}/auth/logout`, {
    credentials: "include",
    method: "POST",
    headers: { "X-CSRF-Token": token },
  });
  authState.csrfToken = null;
}
