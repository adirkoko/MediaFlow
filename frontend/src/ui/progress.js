import { els } from "./elements.js";
import { isActiveStatus, statusPillClass } from "../jobs/helpers.js";
import { clampPercent, formatBps, formatEta } from "../utils/format.js";

export function updateLiveProgress(payload) {
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
