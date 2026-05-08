import { els } from "./elements.js";

export function setMessage(target, message, type = "info") {
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

export function clearMessage(target) {
  if (target === "all") {
    for (const name of ["auth", "preview", "job", "jobs"]) clearMessage(name);
    return;
  }
  setMessage(target, "");
}

export function showCopyToast(message) {
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

function messageElement(target) {
  if (target === "auth") return els.authMessage;
  if (target === "preview") return els.previewMessage;
  if (target === "job") return els.jobMessage;
  if (target === "jobs") return els.jobsMessage;
  return null;
}
