const API_BASE = "http://127.0.0.1:8000";

const els = {
  username: document.getElementById("username"),
  password: document.getElementById("password"),
  tokenStatus: document.getElementById("token-status"),
  tokenPill: document.getElementById("token-pill"),
  btnLogin: document.getElementById("btn-login"),
  btnLogout: document.getElementById("btn-logout"),
  jobUrl: document.getElementById("job-url"),
  jobMode: document.getElementById("job-mode"),
  jobQuality: document.getElementById("job-quality"),
  btnCreate: document.getElementById("btn-create"),
  createResult: document.getElementById("create-result"),
  btnRefresh: document.getElementById("btn-refresh"),
  jobsBody: document.getElementById("jobs-body"),
  jobDetail: document.getElementById("job-detail"),
  btnDownload: document.getElementById("btn-download"),
  btnReport: document.getElementById("btn-report"),
  btnLive: document.getElementById("btn-live"),
  btnStopLive: document.getElementById("btn-stop-live"),
  events: document.getElementById("events"),
  toast: document.getElementById("toast"),
  liveBar: document.getElementById("live-bar"),
  liveStage: document.getElementById("live-stage"),
  livePercent: document.getElementById("live-percent"),
  liveEta: document.getElementById("live-eta"),
  liveSpeed: document.getElementById("live-speed"),
  liveStatus: document.getElementById("live-status"),
  errorBanner: document.getElementById("error-banner"),
};

let selectedJobId = null;
let liveAbort = null;

function getToken() {
  return localStorage.getItem("mf_token");
}

function setToken(token) {
  if (token) {
    localStorage.setItem("mf_token", token);
  } else {
    localStorage.removeItem("mf_token");
  }
  updateTokenStatus();
}

function updateTokenStatus() {
  const present = getToken();
  els.tokenStatus.textContent = present ? "present" : "missing";
  if (els.tokenPill) {
    els.tokenPill.textContent = `Token: ${present ? "present" : "missing"}`;
    els.tokenPill.className = present
      ? "rounded-full bg-emerald-100 px-3 py-1 text-xs text-emerald-700"
      : "rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600";
  }
}

function showError(message) {
  if (!els.errorBanner) return;
  els.errorBanner.textContent = message;
  els.errorBanner.classList.remove("hidden");
}

function clearError() {
  if (!els.errorBanner) return;
  els.errorBanner.textContent = "";
  els.errorBanner.classList.add("hidden");
}

function authHeaders() {
  const token = getToken();
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

async function api(path, options = {}) {
  setBusy(true);
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(options.headers || {}),
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
    setBusy(false);
    const msg = data?.detail || res.statusText;
    throw new Error(msg);
  }
  setBusy(false);
  return data;
}

function showToast(message, isError = false) {
  if (!els.toast) return;
  if (isError) return;
  els.toast.textContent = message;
  els.toast.classList.remove("hidden");
  els.toast.className =
    "fixed bottom-6 right-6 rounded-2xl bg-slate-900 px-4 py-3 text-sm text-white shadow-xl";
  setTimeout(() => els.toast.classList.add("hidden"), 2000);
}

function setBusy(isBusy) {
  const buttons = [
    els.btnLogin,
    els.btnLogout,
    els.btnCreate,
    els.btnRefresh,
    els.btnDownload,
    els.btnReport,
    els.btnLive,
    els.btnStopLive,
  ];
  for (const b of buttons) {
    if (!b) continue;
    b.disabled = isBusy;
    b.classList.toggle("opacity-60", isBusy);
    b.classList.toggle("cursor-not-allowed", isBusy);
  }
}

async function login() {
  const payload = {
    username: els.username.value.trim(),
    password: els.password.value,
  };
  const data = await api("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  setToken(data.access_token);
  showToast("Logged in");
}

async function createJob() {
  const payload = {
    url: els.jobUrl.value.trim(),
    mode: els.jobMode.value,
    quality: els.jobQuality.value.trim() || "best",
  };
  const data = await api("/jobs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  els.createResult.textContent = `Created job ${data.job_id} (reused=${data.reused})`;
  await refreshJobs();
  selectJob(data.job_id);
  showToast("Job created");
}

async function refreshJobs() {
  const jobs = await api("/jobs");
  els.jobsBody.innerHTML = "";
  for (const j of jobs) {
    const tr = document.createElement("tr");
    tr.className = `border-b ${statusRowClass(j.status)}`;
    tr.innerHTML = `
      <td class="py-2 font-mono text-xs">${j.job_id}</td>
      <td><span class="${statusPillClass(j.status)}">${j.status}</span></td>
      <td>${j.mode}</td>
      <td>${j.quality}</td>
      <td>${j.updated_at || "-"}</td>
      <td>
        <button data-id="${j.job_id}" class="select-job btn text-xs">
          Select
        </button>
      </td>
    `;
    els.jobsBody.appendChild(tr);
  }
}

function statusPillClass(status) {
  if (status === "succeeded") return "rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] text-emerald-700";
  if (status === "failed") return "rounded-full bg-rose-100 px-2 py-0.5 text-[11px] text-rose-700";
  if (status === "running") return "rounded-full bg-blue-100 px-2 py-0.5 text-[11px] text-blue-700";
  if (status === "queued") return "rounded-full bg-amber-100 px-2 py-0.5 text-[11px] text-amber-700";
  return "rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600";
}

function statusRowClass(status) {
  if (status === "succeeded") return "bg-emerald-50/40";
  if (status === "failed") return "bg-rose-50/40";
  if (status === "running") return "bg-blue-50/40";
  if (status === "queued") return "bg-amber-50/40";
  return "";
}

async function selectJob(jobId) {
  selectedJobId = jobId;
  const job = await api(`/jobs/${jobId}`);
  els.jobDetail.textContent = JSON.stringify(job, null, 2);
  showToast(`Selected ${jobId}`);
}

async function downloadOutput() {
  if (!selectedJobId) return;
  const res = await fetch(`${API_BASE}/jobs/${selectedJobId}/download`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `job-${selectedJobId}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  showToast("Download started");
}

async function downloadReport() {
  if (!selectedJobId) return;
  const res = await fetch(`${API_BASE}/jobs/${selectedJobId}/report`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `report-${selectedJobId}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  showToast("Report download started");
}

function appendEvent(text) {
  const div = document.createElement("div");
  div.textContent = text;
  els.events.prepend(div);
}

function updateLiveProgress(payload) {
  if (!payload) return;
  const pct = typeof payload.progress_percent === "number" ? payload.progress_percent : 0;
  const stage = payload.stage || "running";
  const status = payload.status || "running";
  const etaSeconds =
    typeof payload.eta_seconds === "number" && payload.eta_seconds >= 0
      ? payload.eta_seconds
      : null;
  const speedBps =
    typeof payload.speed_bps === "number" && payload.speed_bps > 0
      ? payload.speed_bps
      : null;

  if (els.liveBar) {
    els.liveBar.style.width = `${Math.min(100, Math.max(0, pct))}%`;
  }
  if (els.liveStage) {
    els.liveStage.textContent = stage;
  }
  if (els.livePercent) {
    els.livePercent.textContent = `${Math.min(100, Math.max(0, pct))}%`;
  }
  if (els.liveEta) {
    els.liveEta.textContent = `ETA: ${etaSeconds !== null ? formatEta(etaSeconds) : "--"}`;
  }
  if (els.liveSpeed) {
    els.liveSpeed.textContent = `Speed: ${speedBps !== null ? formatBps(speedBps) : "--"}`;
  }
  if (els.liveStatus) {
    els.liveStatus.textContent = status;
    if (status === "succeeded") {
      els.liveStatus.className =
        "rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] text-emerald-700";
    } else if (status === "failed") {
      els.liveStatus.className =
        "rounded-full bg-rose-100 px-2 py-0.5 text-[11px] text-rose-700";
    } else if (status === "running") {
      els.liveStatus.className =
        "rounded-full bg-blue-100 px-2 py-0.5 text-[11px] text-blue-700";
    } else if (status === "queued") {
      els.liveStatus.className =
        "rounded-full bg-amber-100 px-2 py-0.5 text-[11px] text-amber-700";
    } else {
      els.liveStatus.className =
        "rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600";
    }
  }
}

function formatEta(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  const m = Math.floor(s / 60);
  const r = s % 60;
  if (m === 0) return `${r}s`;
  return `${m}m ${r}s`;
}

function formatBps(bps) {
  const units = ["B/s", "KB/s", "MB/s", "GB/s"];
  let v = bps;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(1)} ${units[i]}`;
}
async function liveProgress() {
  if (!selectedJobId) return;
  if (liveAbort) liveAbort.abort();
  liveAbort = new AbortController();
  els.events.innerHTML = "";
  updateLiveProgress({ progress_percent: 0, stage: "connecting", status: "running" });
  showToast("Live stream started");

  const res = await fetch(`${API_BASE}/jobs/${selectedJobId}/events`, {
    headers: authHeaders(),
    signal: liveAbort.signal,
  });
  if (!res.ok || !res.body) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const line = chunk.split("\n").find((l) => l.startsWith("data: "));
      if (line) {
        const json = line.replace("data: ", "");
        appendEvent(json);
        try {
          const payload = JSON.parse(json);
          updateLiveProgress(payload);
        } catch {
          // ignore malformed chunks
        }
      }
    }
  }
}

function stopLive() {
  if (liveAbort) {
    liveAbort.abort();
    liveAbort = null;
    showToast("Live stream stopped");
  }
  updateLiveProgress({ progress_percent: 0, stage: "idle", status: "idle" });
}

function bindEvents() {
  els.btnLogin.addEventListener("click", async () => {
    try {
      clearError();
      await login();
    } catch (err) {
      showError(err.message);
    }
  });

  els.btnLogout.addEventListener("click", () => setToken(null));

  els.btnCreate.addEventListener("click", async () => {
    try {
      clearError();
      await createJob();
    } catch (err) {
      showError(err.message);
    }
  });

  els.btnRefresh.addEventListener("click", async () => {
    try {
      clearError();
      await refreshJobs();
    } catch (err) {
      showError(err.message);
    }
  });

  els.jobsBody.addEventListener("click", async (e) => {
    const btn = e.target.closest(".select-job");
    if (!btn) return;
    try {
      clearError();
      await selectJob(btn.dataset.id);
    } catch (err) {
      showError(err.message);
    }
  });

  els.btnDownload.addEventListener("click", async () => {
    try {
      clearError();
      await downloadOutput();
    } catch (err) {
      showError(err.message);
    }
  });

  els.btnReport.addEventListener("click", async () => {
    try {
      clearError();
      await downloadReport();
    } catch (err) {
      showError(err.message);
    }
  });

  els.btnLive.addEventListener("click", async () => {
    try {
      clearError();
      await liveProgress();
    } catch (err) {
      showError(err.message);
    }
  });

  els.btnStopLive.addEventListener("click", stopLive);
}

function init() {
  updateTokenStatus();
  initNavigation();
  bindEvents();
}

init();

function initNavigation() {
  const buttons = Array.from(document.querySelectorAll(".nav-btn"));
  const sections = Array.from(document.querySelectorAll(".section"));

  function setActive(sectionName) {
    for (const s of sections) {
      s.classList.toggle("hidden", s.id !== `section-${sectionName}`);
    }
    for (const b of buttons) {
      b.classList.toggle("active", b.dataset.section === sectionName);
    }
  }

  for (const b of buttons) {
    b.addEventListener("click", () => setActive(b.dataset.section));
  }

  setActive("dashboard");
}
