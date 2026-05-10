import { api } from "./api/client.js";
import { renderJobs, renderSelectedJob, refreshJobs, stopLive } from "./jobs/index.js";
import { renderPreview } from "./preview.js";
import { getCurrentUserFromToken, getToken, setToken } from "./session.js";
import { state } from "./state.js";
import { els } from "./ui/elements.js";
import { clearMessage, setMessage } from "./ui/messages.js";

export function updateTokenStatus() {
  const present = Boolean(getToken());
  const user = getCurrentUserFromToken();
  els.tokenPill.textContent = present
    ? `Signed in${user?.role === "admin" ? " - admin" : ""}`
    : "Signed out";
  els.tokenPill.className = present
    ? "rounded-full bg-emerald-100 px-3 py-1 text-xs text-emerald-700"
    : "rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600";
}

export async function login() {
  const data = await api("/auth/login", {
    method: "POST",
    body: JSON.stringify({
      username: els.username.value.trim(),
      password: els.password.value,
    }),
  });
  setToken(data.access_token);
  updateTokenStatus();
  els.password.value = "";
  await refreshJobs({ silent: true });
  setMessage("auth", "Logged in.", "success");
}

export function logout() {
  stopLive();
  setToken(null);
  updateTokenStatus();
  state.preview = null;
  state.jobs = [];
  state.selectedJob = null;
  state.selectedJobId = null;
  renderPreview();
  renderJobs();
  renderSelectedJob();
  clearMessage("preview");
  clearMessage("job");
  clearMessage("jobs");
  setMessage("auth", "Logged out.", "info");
}
