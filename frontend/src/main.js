import "./styles/main.css";

import { login, logout, updateTokenStatus } from "./auth.js";
import { updateApiBadge } from "./config.js";
import {
  cancelJob,
  copyJobStats,
  downloadOutput,
  refreshJobs,
  renderJobs,
  renderSelectedJob,
  selectJob,
  startSmartRefresh,
} from "./jobs/index.js";
import {
  createJob,
  loadPreview,
  renderPreview,
  schedulePreview,
  setMode,
} from "./preview.js";
import { state } from "./state.js";
import { els } from "./ui/elements.js";
import { clearMessage, setMessage } from "./ui/messages.js";

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
}

function init() {
  updateApiBadge(els.apiBaseLabel);
  updateTokenStatus();
  bindEvents();
  renderPreview();
  renderJobs();
  renderSelectedJob();
  startSmartRefresh();
}

init();
