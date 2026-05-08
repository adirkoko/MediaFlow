import { api } from "./api/client.js";
import { refreshJobs, selectJob } from "./jobs/index.js";
import { getToken } from "./session.js";
import { FALLBACK_VIDEO_QUALITIES, state } from "./state.js";
import { els } from "./ui/elements.js";
import { clearMessage, setMessage } from "./ui/messages.js";
import { formatBytes, formatDuration, hostFromUrl } from "./utils/format.js";

export function schedulePreview() {
  window.clearTimeout(state.previewTimer);
  const url = els.jobUrl.value.trim();
  if (url.length < 5) {
    state.preview = null;
    renderPreview();
    return;
  }
  state.previewTimer = window.setTimeout(() => loadPreview(), 750);
}

export async function loadPreview() {
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

export function renderPreview() {
  const hasPreview = Boolean(state.preview);
  els.previewEmpty.classList.toggle(
    "hidden",
    hasPreview || !els.previewLoading.classList.contains("hidden"),
  );
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
  els.previewMeta.textContent = [
    p.uploader,
    p.webpage_url ? hostFromUrl(p.webpage_url) : null,
  ]
    .filter(Boolean)
    .join(" / ");

  els.modeAudio.classList.toggle("active", state.mode === "audio");
  els.modeVideo.classList.toggle("active", state.mode === "video");
  renderQualityOptions();
  renderEstimatedSize();
}

export function setMode(mode) {
  state.mode = mode;
  if (mode === "audio") state.quality = "best";
  renderPreview();
}

export async function createJob() {
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

function setPreviewLoading(isLoading) {
  els.previewLoading.classList.toggle("hidden", !isLoading);
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
