export function getToken() {
  return localStorage.getItem("mf_token");
}

export function setToken(token) {
  if (token) {
    localStorage.setItem("mf_token", token);
  } else {
    localStorage.removeItem("mf_token");
  }
  window.dispatchEvent(new CustomEvent("mediaflow:auth-changed"));
}

export function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function getTokenPayload() {
  const token = getToken();
  if (!token) return null;
  const [, payload] = token.split(".");
  if (!payload) return null;

  try {
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(
      normalized.length + ((4 - (normalized.length % 4)) % 4),
      "=",
    );
    return JSON.parse(window.atob(padded));
  } catch {
    return null;
  }
}

export function getCurrentUserFromToken() {
  const payload = getTokenPayload();
  if (!payload) return null;
  return {
    id: payload.sub ? String(payload.sub) : "",
    username: payload.username ? String(payload.username) : "",
    role: payload.role ? String(payload.role) : "",
    tokenVersion: payload.token_version,
  };
}

export function isCurrentUserAdmin() {
  return getCurrentUserFromToken()?.role === "admin";
}
