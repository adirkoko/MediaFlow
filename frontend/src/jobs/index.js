import { API_BASE, api } from "../api/client.js";
import { state } from "../state.js";
import { authHeaders, getToken } from "../session.js";
import { els } from "../ui/elements.js";
import { clearMessage, setMessage, showCopyToast } from "../ui/messages.js";
import { updateLiveProgress } from "../ui/progress.js";
import {
  escapeHtml,
  renderFactValue,
  shortJobId,
  timestampHtml,
} from "../utils/format.js";
import { isActiveJob, isActiveStatus, outputLabel, statusPillClass } from "./helpers.js";

export async function refreshJobs({ silent = false } = {}) {
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

export async function selectJob(jobId, { silent = false } = {}) {
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

export function renderJobs() {
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

export function renderSelectedJob() {
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

export async function cancelJob() {
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

export async function downloadOutput() {
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

export async function copyJobStats() {
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

export function startSmartRefresh() {
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

export function stopLive(reset = true) {
  if (state.liveAbort) {
    state.liveAbort.abort();
    state.liveAbort = null;
  }
  state.liveJobId = null;
  if (reset && !state.selectedJob) {
    updateLiveProgress({ progress_percent: 0, stage: "idle", status: "idle" });
  }
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

function renderRefreshLabel() {
  const active = state.jobs.some(isActiveJob) || isActiveJob(state.selectedJob);
  const base = state.lastRefreshAt ? `Updated ${timestampHtml(state.lastRefreshAt)}` : "Idle";
  els.refreshLabel.innerHTML = active ? `${base} / live` : base;
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
