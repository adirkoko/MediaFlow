export const state = {
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

export const FALLBACK_VIDEO_QUALITIES = [
  { quality: "best", height: null },
  { quality: "720p", height: 720 },
  { quality: "1080p", height: 1080 },
];
