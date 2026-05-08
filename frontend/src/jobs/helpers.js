export function isActiveJob(job) {
  return Boolean(job && isActiveStatus(job.status));
}

export function isActiveStatus(status) {
  return status === "queued" || status === "running";
}

export function outputLabel(job) {
  if (job.output_filename) return job.output_filename;
  if (job.error_code) return job.error_code;
  return job.stage || job.url || job.job_id;
}

export function statusPillClass(status) {
  if (status === "succeeded") {
    return "rounded-full bg-emerald-100 px-2.5 py-1 text-xs text-emerald-700";
  }
  if (status === "failed") {
    return "rounded-full bg-rose-100 px-2.5 py-1 text-xs text-rose-700";
  }
  if (status === "canceled") {
    return "rounded-full bg-slate-200 px-2.5 py-1 text-xs text-slate-700";
  }
  if (status === "running") {
    return "rounded-full bg-blue-100 px-2.5 py-1 text-xs text-blue-700";
  }
  if (status === "queued") {
    return "rounded-full bg-amber-100 px-2.5 py-1 text-xs text-amber-700";
  }
  return "rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-600";
}
