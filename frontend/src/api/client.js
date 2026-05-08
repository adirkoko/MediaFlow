import { API_BASE } from "../config.js";
import { authHeaders } from "../session.js";

export { API_BASE };

export async function api(path, options = {}) {
  const { silent = false, ...fetchOptions } = options;
  void silent;

  const res = await fetch(`${API_BASE}${path}`, {
    ...fetchOptions,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(fetchOptions.headers || {}),
    },
  });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const detail = Array.isArray(data?.detail)
      ? data.detail.map((d) => d.msg || String(d)).join(", ")
      : data?.detail || data || res.statusText;
    throw new Error(detail);
  }
  return data;
}
