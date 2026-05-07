const API_BASE = resolveApiBase();

const els = {
  username: document.getElementById("username"),
  password: document.getElementById("password"),
  authMessage: document.getElementById("auth-message"),
  tokenPill: document.getElementById("token-pill"),
  btnLogin: document.getElementById("btn-login"),
  btnLogout: document.getElementById("btn-logout"),
  jobUrl: document.getElementById("job-url"),
  btnPreview: document.getElementById("btn-preview"),
  previewLoading: document.getElementById("preview-loading"),
  previewEmpty: document.getElementById("preview-empty"),
  previewCard: document.getElementById("preview-card"),
  previewThumb: document.getElementById("preview-thumb"),
  previewKind: document.getElementById("preview-kind"),
  previewDuration: document.getElementById("preview-duration"),
  previewSize: document.getElementById("preview-size"),
  previewMessage: document.getElementById("preview-message"),
  previewTitle: document.getElementById("preview-title"),
  previewMeta: document.getElementById("preview-meta"),
  modeAudio: document.getElementById("mode-audio"),
  modeVideo: document.getElementById("mode-video"),
  qualityPanel: document.getElementById("quality-panel"),
  qualityOptions: document.getElementById("quality-options"),
  qualityNote: document.getElementById("quality-note"),
  btnCreate: document.getElementById("btn-create"),
  createResult: document.getElementById("create-result"),
  selectedJobLabel: document.getElementById("selected-job-label"),
  btnCancel: document.getElementById("btn-cancel"),
  btnDownload: document.getElementById("btn-download"),
  btnCopyStats: document.getElementById("btn-copy-stats"),
  btnRefresh: document.getElementById("btn-refresh"),
  jobsList: document.getElementById("jobs-list"),
  jobsMessage: document.getElementById("jobs-message"),
  refreshLabel: document.getElementById("refresh-label"),
  liveBar: document.getElementById("live-bar"),
  liveStage: document.getElementById("live-stage"),
  livePercent: document.getElementById("live-percent"),
  liveEta: document.getElementById("live-eta"),
  liveSpeed: document.getElementById("live-speed"),
  liveStatus: document.getElementById("live-status"),
  jobFacts: document.getElementById("job-facts"),
  jobOutput: document.getElementById("job-output"),
  jobMessage: document.getElementById("job-message"),
  copyToast: document.getElementById("copy-toast"),
};

const state = {
  preview: null,
  mode: "audio",
  quality: "best",
  jobs: [],
  selectedJobId: null,
  selectedJob: null,
  previewTimer: null,
  previewRequestId: 0,
  liveAbort: null,
  liveJobId: null,
  refreshTimer: null,
  lastRefreshAt: null,
  jobsRenderKey: "",
  selectedJobRenderKey: "",
};

const FALLBACK_VIDEO_QUALITIES = [
  { quality: "best", height: null },
  { quality: "720p", height: 720 },
  { quality: "1080p", height: 1080 },
];

function resolveApiBase() {
  const runtime = window.MEDIAFLOW_API_BASE;
  if (typeof runtime === "string" && runtime.trim().length > 0) {
    return runtime.trim().replace(/\/+$/, "");
  }
  return "/api";
}

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

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function api(path, options = {}) {
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

function updateApiBadge() {
  const el = document.getElementById("api-base-label");
  if (el) el.textContent = API_BASE.replace(/^https?:\/\//, "");
}

function updateTokenStatus() {
  const present = Boolean(getToken());
  els.tokenPill.textContent = present ? "Signed in" : "Signed out";
  els.tokenPill.className = present
    ? "rounded-full bg-emerald-100 px-3 py-1 text-xs text-emerald-700"
    : "rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600";
}

function setMessage(target, message, type = "info") {
  const el = messageElement(target);
  if (!el) return;
  if (!message) {
    el.textContent = "";
    el.className = "hidden text-sm";
    return;
  }

  const tone =
    type === "error"
      ? "border-rose-200 bg-rose-50 text-rose-700"
      : type === "success"
        ? "border-emerald-200 bg-emerald-50 text-emerald-700"
        : "border-slate-200 bg-slate-50 text-slate-600";
  el.textContent = message;
  el.className = `rounded-lg border px-3 py-2 text-sm ${tone}`;
}

function messageElement(target) {
  if (target === "auth") return els.authMessage;
  if (target === "preview") return els.previewMessage;
  if (target === "job") return els.jobMessage;
  if (target === "jobs") return els.jobsMessage;
  return null;
}

function clearMessage(target) {
  if (target === "all") {
    for (const name of ["auth", "preview", "job", "jobs"]) clearMessage(name);
    return;
  }
  setMessage(target, "");
}

async function login() {
  const data = await api("/auth/login", {
    method: "POST",
    body: JSON.stringify({
      username: els.username.value.trim(),
      password: els.password.value,
    }),
  });
  setToken(data.access_token);
  els.password.value = "";
  await refreshJobs({ silent: true });
  setMessage("auth", "Logged in.", "success");
}

function logout() {
  stopLive();
  setToken(null);
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

function schedulePreview() {
  window.clearTimeout(state.previewTimer);
  const url = els.jobUrl.value.trim();
  if (url.length < 5) {
    state.preview = null;
    renderPreview();
    return;
  }
  state.previewTimer = window.setTimeout(() => loadPreview(), 750);
}

async function loadPreview() {
  const url = els.jobUrl.value.trim();
  if (!url) return;
  if (!getToken()) {
    setMessage("preview", "Login required before preview.", "error");
    return;
  }

  const requestId = ++state.previewRequestId;
  clearMessage("preview");
  state.preview = null;
  setPreviewLoading(true);
  renderPreview();

  try {
    const preview = await api("/jobs/preview", {
      method: "POST",
      body: JSON.stringify({ url }),
    });
    if (requestId !== state.previewRequestId) return;
    state.preview = preview;
    state.mode = "audio";
    state.quality = "best";
    renderPreview();
    setMessage("preview", "Preview loaded.", "success");
  } catch (err) {
    if (requestId === state.previewRequestId) {
      setMessage("preview", err.message, "error");
    }
  } finally {
    if (requestId === state.previewRequestId) setPreviewLoading(false);
  }
}

function setPreviewLoading(isLoading) {
  els.previewLoading.classList.toggle("hidden", !isLoading);
}

function renderPreview() {
  const hasPreview = Boolean(state.preview);
  els.previewEmpty.classList.toggle("hidden", hasPreview || !els.previewLoading.classList.contains("hidden"));
  els.previewCard.classList.toggle("hidden", !hasPreview);
  els.btnCreate.disabled = !hasPreview;
  els.btnCreate.classList.toggle("opacity-60", !hasPreview);
  els.btnCreate.classList.toggle("cursor-not-allowed", !hasPreview);
  els.createResult.textContent = "";

  if (!hasPreview) return;

  const p = state.preview;
  const thumb = p.thumbnail || "";
  els.previewThumb.src = thumb;
  els.previewThumb.classList.toggle("hidden", !thumb);
  els.previewKind.textContent = p.is_playlist ? "playlist" : "video";
  els.previewDuration.textContent = p.is_playlist
    ? `${p.playlist_count || 0} items`
    : formatDuration(p.duration_seconds);
  els.previewTitle.textContent = p.title || "Untitled";
  els.previewMeta.textContent = [p.uploader, p.webpage_url ? hostFromUrl(p.webpage_url) : null]
    .filter(Boolean)
    .join(" / ");

  els.modeAudio.classList.toggle("active", state.mode === "audio");
  els.modeVideo.classList.toggle("active", state.mode === "video");
  renderQualityOptions();
  renderEstimatedSize();
}

function renderQualityOptions() {
  const isVideo = state.mode === "video";
  els.qualityPanel.classList.toggle("hidden", !isVideo);
  els.qualityOptions.innerHTML = "";
  if (!isVideo) {
    state.quality = "best";
    return;
  }

  const qualities = videoQualities();
  if (!qualities.some((q) => q.quality === state.quality)) {
    state.quality = qualities[0]?.quality || "best";
  }

  els.qualityNote.textContent = state.preview?.video_qualities?.length
    ? "Available now"
    : "Per item";

  for (const q of qualities) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `quality-btn px-3 py-2 text-sm font-semibold ${
      q.quality === state.quality ? "active" : ""
    }`;
    button.dataset.quality = q.quality;
    const size = q.filesize_bytes ? ` / ${formatBytes(q.filesize_bytes)}` : "";
    button.textContent = `${q.quality}${size}`;
    els.qualityOptions.appendChild(button);
  }
}

function videoQualities() {
  const fromPreview = state.preview?.video_qualities || [];
  if (fromPreview.length > 0) return fromPreview;
  return FALLBACK_VIDEO_QUALITIES;
}

function renderEstimatedSize() {
  if (!state.preview) {
    els.previewSize.textContent = "--";
    return;
  }
  if (state.mode === "audio") {
    els.previewSize.textContent = state.preview.audio_filesize_bytes
      ? `Audio ${formatBytes(state.preview.audio_filesize_bytes)}`
      : "Audio size unknown";
    return;
  }
  const selected = videoQualities().find((q) => q.quality === state.quality);
  els.previewSize.textContent = selected?.filesize_bytes
    ? `Video ${formatBytes(selected.filesize_bytes)}`
    : "Video size unknown";
}

function setMode(mode) {
  state.mode = mode;
  if (mode === "audio") state.quality = "best";
  renderPreview();
}

async function createJob() {
  if (!state.preview) return;
  const payload = {
    url: state.preview.url,
    mode: state.mode,
    quality: state.mode === "audio" ? "best" : state.quality || "best",
  };
  clearMessage("preview");
  const data = await api("/jobs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  els.createResult.textContent = data.reused ? "Existing job selected" : "Job queued";
  await refreshJobs({ silent: true });
  await selectJob(data.job_id, { silent: true });
  setMessage("preview", data.reused ? "Existing job selected." : "Job queued.", "success");
}

async function refreshJobs({ silent = false } = {}) {
  if (!getToken()) {
    state.jobs = [];
    renderJobs();
    return;
  }
  const jobs = await api("/jobs", { silent });
  state.jobs = Array.isArray(jobs) ? jobs : [];
  state.lastRefreshAt = new Date();
  renderJobs();
  renderRefreshLabel();

  if (!state.selectedJobId && state.jobs.length > 0) {
    await selectJob(state.jobs[0].job_id, { silent: true });
  }
}

async function selectJob(jobId, { silent = false } = {}) {
  const isDifferentJob = state.selectedJobId !== jobId;
  if (isDifferentJob) {
    clearMessage("job");
  }
  state.selectedJobId = jobId;
  const job = await api(`/jobs/${jobId}`, { silent });
  state.selectedJob = job;
  renderSelectedJob();
  renderJobs();
  if (isActiveJob(job)) startLive(jobId);
}

function renderJobs() {
  const renderKey = JSON.stringify({
    selected: state.selectedJobId,
    signedIn: Boolean(getToken()),
    jobs: state.jobs.map((job) => ({
      id: job.job_id,
      status: job.status,
      mode: job.mode,
      quality: job.quality,
      updated_at: job.updated_at,
      created_at: job.created_at,
      output_filename: job.output_filename,
      output_type: job.output_type,
      error_code: job.error_code,
      stage: job.stage,
    })),
  });
  if (renderKey === state.jobsRenderKey) return;
  state.jobsRenderKey = renderKey;

  els.jobsList.innerHTML = "";
  if (!getToken()) {
    els.jobsList.innerHTML = `<div class="soft p-4 text-sm text-slate-500">Signed out</div>`;
    return;
  }
  if (state.jobs.length === 0) {
    els.jobsList.innerHTML = `<div class="soft p-4 text-sm text-slate-500">No jobs yet</div>`;
    return;
  }

  for (const job of state.jobs) {
    const row = document.createElement("button");
    row.type = "button";
    row.dataset.id = job.job_id;
    row.className = `job-row grid gap-2 p-3 text-left ${
      job.job_id === state.selectedJobId ? "active" : ""
    } ${isActiveJob(job) ? "running-mark" : ""}`;
    row.innerHTML = `
      <div class="flex items-center justify-between gap-3">
        <span class="truncate font-mono text-xs text-slate-500">${shortJobId(job.job_id)}</span>
        <span class="${statusPillClass(job.status)}">${job.status}</span>
      </div>
      <div class="min-w-0 truncate text-sm font-semibold text-slate-800">${escapeHtml(outputLabel(job))}</div>
      <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
        <span>${job.mode}</span>
        <span>${job.quality}</span>
        <span>${timestampHtml(job.updated_at || job.created_at)}</span>
      </div>
    `;
    els.jobsList.appendChild(row);
  }
}

function renderSelectedJob() {
  const job = state.selectedJob;
  if (!job) {
    if (state.selectedJobRenderKey === "none") return;
    state.selectedJobRenderKey = "none";
    els.selectedJobLabel.textContent = "No job selected";
    updateLiveProgress({ progress_percent: 0, stage: "idle", status: "idle" });
    els.jobFacts.innerHTML = "";
    els.jobOutput.innerHTML = "";
    els.jobOutput.classList.add("hidden");
    for (const button of [els.btnCancel, els.btnDownload, els.btnCopyStats]) {
      button.disabled = true;
      button.classList.add("opacity-60");
    }
    return;
  }

  const renderKey = JSON.stringify({
    job_id: job.job_id,
    status: job.status,
    mode: job.mode,
    quality: job.quality,
    created_at: job.created_at,
    updated_at: job.updated_at,
    started_at: job.started_at,
    finished_at: job.finished_at,
    output_filename: job.output_filename,
    output_type: job.output_type,
    error_code: job.error_code,
    error_message: job.error_message,
    playlist_total: job.playlist_total,
    playlist_succeeded: job.playlist_succeeded,
    playlist_failed: job.playlist_failed,
  });
  if (renderKey === state.selectedJobRenderKey) {
    updateLiveProgress(job);
    return;
  }
  state.selectedJobRenderKey = renderKey;

  els.selectedJobLabel.textContent = `${shortJobId(job.job_id)} / ${job.mode} / ${job.quality}`;
  updateLiveProgress(job);
  const facts = [
    ["Created", timestampHtml(job.created_at)],
    ["Updated", timestampHtml(job.updated_at || job.finished_at || job.started_at)],
  ];
  if (typeof job.playlist_total === "number") {
    facts.push(["Playlist", `${job.playlist_succeeded || 0}/${job.playlist_total} ok`]);
  }
  if (job.error_code || job.error_message) {
    facts.push(["Error", job.error_code || job.error_message]);
  }
  els.jobFacts.innerHTML = facts
    .map(
      ([label, value]) => `
      <div class="rounded-lg bg-white/70 p-3">
        <div class="text-[11px] uppercase tracking-wide text-slate-400">${escapeHtml(label)}</div>
        <div class="mt-1 break-words text-sm font-medium text-slate-700">${renderFactValue(value)}</div>
      </div>
    `,
    )
    .join("");

  const output = job.output_filename || job.output_type;
  if (output) {
    els.jobOutput.classList.remove("hidden");
    els.jobOutput.innerHTML = `
      <div class="text-[11px] uppercase tracking-wide text-slate-400">Output</div>
      <div class="mt-1 break-all font-mono text-sm font-medium text-slate-800">${escapeHtml(output)}</div>
    `;
  } else {
    els.jobOutput.innerHTML = "";
    els.jobOutput.classList.add("hidden");
  }

  els.btnCancel.disabled = !isActiveJob(job);
  els.btnCancel.classList.toggle("opacity-60", els.btnCancel.disabled);
  els.btnDownload.disabled = job.status !== "succeeded";
  els.btnDownload.classList.toggle("opacity-60", els.btnDownload.disabled);
  els.btnCopyStats.disabled = false;
  els.btnCopyStats.classList.toggle("opacity-60", false);
  els.btnCopyStats.title = "Copy the selected job payload as formatted JSON";
}

async function cancelJob() {
  if (!state.selectedJobId) return;
  const data = await api(`/jobs/${state.selectedJobId}/cancel`, { method: "POST" });
  await selectJob(state.selectedJobId, { silent: true });
  await refreshJobs({ silent: true });
  setMessage(
    "job",
    data.status === "running" ? "Cancel requested." : "Job canceled.",
    "info",
  );
}

async function downloadOutput() {
  if (!state.selectedJobId) return;
  const job = state.selectedJob || (await api(`/jobs/${state.selectedJobId}`));
  const filename = job?.output_filename || null;
  const res = await fetch(`${API_BASE}/jobs/${state.selectedJobId}/download`, {
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
  a.download =
    filename || filenameFromContentDisposition(res) || `download-${state.selectedJobId}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  await refreshJobs({ silent: true });
  setMessage("job", "Download started.", "success");
}

function filenameFromContentDisposition(res) {
  const header = res.headers.get("Content-Disposition");
  if (!header) return null;

  const utf8Match = header.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match) {
    try {
      return decodeURIComponent(utf8Match[1].trim().replace(/^"|"$/g, ""));
    } catch {
      return utf8Match[1].trim().replace(/^"|"$/g, "");
    }
  }

  const asciiMatch = header.match(/filename="?([^";]+)"?/i);
  return asciiMatch ? asciiMatch[1].trim() : null;
}

async function copyJobStats() {
  if (!state.selectedJobId) return;
  const job = await api(`/jobs/${state.selectedJobId}`, { silent: true });
  state.selectedJob = job;
  renderSelectedJob();

  const text = JSON.stringify(job, null, 2);
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
  } else {
    copyTextFallback(text);
  }
  showCopyToast("Copied");
}

function showCopyToast(message) {
  if (!els.copyToast) return;
  els.copyToast.textContent = message;
  els.copyToast.classList.remove("hidden", "show");
  void els.copyToast.offsetWidth;
  els.copyToast.classList.add("show");
  window.clearTimeout(showCopyToast.timer);
  showCopyToast.timer = window.setTimeout(() => {
    els.copyToast.classList.add("hidden");
    els.copyToast.classList.remove("show");
  }, 1200);
}

function copyTextFallback(text) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

function startLive(jobId) {
  if (!jobId || !getToken()) return;
  if (state.liveAbort && state.liveJobId === jobId) return;
  stopLive(false);
  state.liveJobId = jobId;
  state.liveAbort = new AbortController();
  streamJobEvents(jobId, state.liveAbort.signal).catch((err) => {
    if (err.name !== "AbortError" && state.selectedJobId === jobId) {
      setMessage("job", err.message, "error");
    }
  });
}

async function streamJobEvents(jobId, signal) {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/events`, {
    headers: authHeaders(),
    signal,
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
      if (!line) continue;
      const json = line.replace("data: ", "");
      try {
        const payload = JSON.parse(json);
        if (payload.job_id === state.selectedJobId) {
          state.selectedJob = { ...(state.selectedJob || {}), ...payload };
          updateLiveProgress(state.selectedJob);
        }
        if (payload.status && !isActiveStatus(payload.status)) {
          await refreshJobs({ silent: true });
          await selectJob(jobId, { silent: true });
        }
      } catch {
        // Ignore malformed chunks.
      }
    }
  }
}

function stopLive(reset = true) {
  if (state.liveAbort) {
    state.liveAbort.abort();
    state.liveAbort = null;
  }
  state.liveJobId = null;
  if (reset && !state.selectedJob) {
    updateLiveProgress({ progress_percent: 0, stage: "idle", status: "idle" });
  }
}

function updateLiveProgress(payload) {
  const pct = clampPercent(payload?.progress_percent);
  const status = payload?.status || "idle";
  const stage = payload?.stage || status;
  const eta = typeof payload?.eta_seconds === "number" ? payload.eta_seconds : null;
  const speed = typeof payload?.speed_bps === "number" ? payload.speed_bps : null;

  els.liveBar.style.width = `${pct}%`;
  els.liveStage.textContent = stage;
  els.livePercent.textContent = `${pct}%`;
  els.liveEta.textContent = `ETA ${eta !== null ? formatEta(eta) : "--"}`;
  els.liveSpeed.textContent = `Speed ${speed ? formatBps(speed) : "--"}`;
  els.liveStatus.textContent = status;
  els.liveStatus.className = statusPillClass(status);
  els.liveBar.classList.toggle("running-mark", isActiveStatus(status));
}

function startSmartRefresh() {
  window.clearTimeout(state.refreshTimer);
  const tick = async () => {
    const hasToken = Boolean(getToken());
    const hidden = document.hidden;
    try {
      if (hasToken && !hidden) {
        await refreshJobs({ silent: true });
        if (state.selectedJobId) {
          await selectJob(state.selectedJobId, { silent: true });
        }
      }
    } catch {
      // The visible error surface is reserved for direct user actions.
    } finally {
      const active = state.jobs.some(isActiveJob) || isActiveJob(state.selectedJob);
      state.refreshTimer = window.setTimeout(tick, active ? 3000 : 12000);
      renderRefreshLabel();
    }
  };
  state.refreshTimer = window.setTimeout(tick, 800);
}

function renderRefreshLabel() {
  const active = state.jobs.some(isActiveJob) || isActiveJob(state.selectedJob);
  const base = state.lastRefreshAt
    ? `Updated ${timestampHtml(state.lastRefreshAt)}`
    : "Idle";
  els.refreshLabel.innerHTML = active ? `${base} / live` : base;
}

function isActiveJob(job) {
  return Boolean(job && isActiveStatus(job.status));
}

function isActiveStatus(status) {
  return status === "queued" || status === "running";
}

function statusPillClass(status) {
  if (status === "succeeded") return "rounded-full bg-emerald-100 px-2.5 py-1 text-xs text-emerald-700";
  if (status === "failed") return "rounded-full bg-rose-100 px-2.5 py-1 text-xs text-rose-700";
  if (status === "canceled") return "rounded-full bg-slate-200 px-2.5 py-1 text-xs text-slate-700";
  if (status === "running") return "rounded-full bg-blue-100 px-2.5 py-1 text-xs text-blue-700";
  if (status === "queued") return "rounded-full bg-amber-100 px-2.5 py-1 text-xs text-amber-700";
  return "rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-600";
}

function outputLabel(job) {
  if (job.output_filename) return job.output_filename;
  if (job.error_code) return job.error_code;
  return job.stage || job.url || job.job_id;
}

function shortJobId(jobId) {
  return jobId ? jobId.slice(0, 8) : "--";
}

function clampPercent(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return 0;
  return Math.min(100, Math.max(0, Math.round(value)));
}

function formatDuration(seconds) {
  if (typeof seconds !== "number" || seconds < 0) return "--";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function formatEta(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${r}s`;
  return `${r}s`;
}

function formatBps(bps) {
  return `${formatBytes(bps)}/s`;
}

function formatBytes(bytes) {
  if (typeof bytes !== "number" || bytes <= 0) return "--";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let idx = 0;
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024;
    idx += 1;
  }
  return `${value.toFixed(value >= 10 || idx === 0 ? 0 : 1)} ${units[idx]}`;
}

function formatDate(value) {
  if (!value) return "--";
  const parts = dateTimeParts(value);
  if (!parts) return value;
  return `${parts.date} ${parts.time}`;
}

function renderFactValue(value) {
  if (!value) return "--";
  const text = String(value);
  if (text.startsWith('<span class="timestamp">')) return text;
  return escapeHtml(text);
}

function timestampHtml(value) {
  if (!value) return "--";
  const parts = dateTimeParts(value);
  if (!parts) return escapeHtml(String(value));
  return `<span class="timestamp"><span>${parts.date}</span><span>${parts.time}</span></span>`;
}

function dateTimeParts(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return {
    date: `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(
      date.getDate(),
    )}`,
    time: `${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(
      date.getSeconds(),
    )}`,
  };
}

function formatClock(date) {
  return `${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(
    date.getSeconds(),
  )}`;
}

function pad2(value) {
  return String(value).padStart(2, "0");
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function hostFromUrl(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return null;
  }
}

function bindEvents() {
  els.btnLogin.addEventListener("click", async () => {
    try {
      clearMessage("auth");
      await login();
    } catch (err) {
      setMessage("auth", err.message, "error");
    }
  });

  els.btnLogout.addEventListener("click", logout);

  els.jobUrl.addEventListener("input", schedulePreview);
  els.btnPreview.addEventListener("click", async () => {
    window.clearTimeout(state.previewTimer);
    await loadPreview();
  });

  els.modeAudio.addEventListener("click", () => setMode("audio"));
  els.modeVideo.addEventListener("click", () => setMode("video"));

  els.qualityOptions.addEventListener("click", (event) => {
    const button = event.target.closest("[data-quality]");
    if (!button) return;
    state.quality = button.dataset.quality;
    renderPreview();
  });

  els.btnCreate.addEventListener("click", async () => {
    try {
      await createJob();
    } catch (err) {
      setMessage("preview", err.message, "error");
    }
  });

  els.btnRefresh.addEventListener("click", async () => {
    try {
      clearMessage("jobs");
      await refreshJobs();
    } catch (err) {
      setMessage("jobs", err.message, "error");
    }
  });

  els.jobsList.addEventListener("click", async (event) => {
    const row = event.target.closest("[data-id]");
    if (!row) return;
    try {
      clearMessage("jobs");
      await selectJob(row.dataset.id);
    } catch (err) {
      setMessage("jobs", err.message, "error");
    }
  });

  els.btnCancel.addEventListener("click", async () => {
    try {
      clearMessage("job");
      await cancelJob();
    } catch (err) {
      setMessage("job", err.message, "error");
    }
  });

  els.btnDownload.addEventListener("click", async () => {
    try {
      clearMessage("job");
      await downloadOutput();
    } catch (err) {
      setMessage("job", err.message, "error");
    }
  });

  els.btnCopyStats.addEventListener("click", async () => {
    try {
      clearMessage("job");
      await copyJobStats();
    } catch (err) {
      setMessage("job", err.message, "error");
    }
  });

  document.addEventListener("visibilitychange", renderRefreshLabel);
}

function init() {
  updateApiBadge();
  updateTokenStatus();
  bindEvents();
  renderPreview();
  renderJobs();
  renderSelectedJob();
  startSmartRefresh();
}

init();
