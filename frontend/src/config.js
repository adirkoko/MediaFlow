export const API_BASE = resolveApiBase();

function resolveApiBase() {
  const runtime = window.MEDIAFLOW_API_BASE;
  if (typeof runtime === "string" && runtime.trim().length > 0) {
    return runtime.trim().replace(/\/+$/, "");
  }
  return "/api";
}

export function updateApiBadge(el) {
  if (el) el.textContent = API_BASE.replace(/^https?:\/\//, "");
}
