import { updateTokenStatus } from "../auth.js";
import { getCurrentUserFromToken, getToken, isCurrentUserAdmin, setToken } from "../session.js";
import {
  clampPercent,
  escapeHtml,
  formatBytes,
  shortJobId,
  timestampHtml,
} from "../utils/format.js";
import { adminApi } from "./api.js";

const ROLE_OPTIONS = ["admin", "user"];
const STATUS_OPTIONS = ["active", "disabled", "locked", "deleted"];
const QUALITY_OPTIONS = ["best", "144p", "240p", "360p", "480p", "720p", "1080p", "1440p", "2160p"];
const RANGE_OPTIONS = ["today", "week", "month"];

const QUOTA_FIELDS = [
  ["max_active_jobs", "Active jobs"],
  ["max_jobs_per_day", "Jobs/day"],
  ["max_jobs_per_week", "Jobs/week"],
  ["max_jobs_per_month", "Jobs/month"],
  ["max_credits_per_day", "Credits/day"],
  ["max_credits_per_week", "Credits/week"],
  ["max_credits_per_month", "Credits/month"],
  ["max_playlist_items_per_job", "Playlist items/job"],
  ["max_playlist_items_per_day", "Playlist items/day"],
  ["max_video_duration_seconds", "Max duration sec"],
  ["max_video_quality", "Max quality"],
  ["max_output_mb_per_day", "Output MB/day"],
  ["max_output_mb_per_month", "Output MB/month"],
];

const NAV = [
  ["/admin", "Dashboard", "dashboard"],
  ["/admin/users", "Users", "users"],
  ["/admin/jobs", "Jobs", "jobs"],
  ["/admin/usage", "Usage", "usage"],
  ["/admin/quotas", "Quotas", "quotas"],
  ["/admin/security", "Security", "security"],
  ["/admin/audit", "Audit Logs", "audit"],
];

let flash = null;
let renderCounter = 0;

export function initAdminRouter() {
  document.addEventListener("click", (event) => {
    const link = event.target.closest('a[href^="/admin"]');
    if (!link) return;
    event.preventDefault();
    navigate(link.getAttribute("href"));
  });

  window.addEventListener("popstate", renderAdminRouter);
  window.addEventListener("mediaflow:auth-changed", renderAdminRouter);
  renderAdminRouter();
}

function isAdminPath() {
  return window.location.pathname === "/admin" || window.location.pathname.startsWith("/admin/");
}

function navigate(path) {
  window.history.pushState({}, "", path);
  renderAdminRouter();
}

async function renderAdminRouter() {
  const root = document.getElementById("admin-root");
  const userApp = document.getElementById("user-app");
  if (!root || !userApp) return;

  if (!isAdminPath()) {
    userApp.classList.remove("hidden");
    root.classList.add("hidden");
    root.innerHTML = "";
    return;
  }

  userApp.classList.add("hidden");
  root.classList.remove("hidden");

  if (!getToken()) {
    window.history.replaceState({}, "", "/");
    userApp.classList.remove("hidden");
    root.classList.add("hidden");
    root.innerHTML = "";
    return;
  }

  if (!isCurrentUserAdmin()) {
    renderAccessDenied();
    return;
  }

  const route = resolveRoute();
  const thisRender = ++renderCounter;
  renderShell(route.key, route.title, loadingBlock("Loading"));

  try {
    await route.render();
  } catch (err) {
    if (thisRender !== renderCounter) return;
    handleRouteError(route, err);
  }
}

function resolveRoute() {
  const path = window.location.pathname.replace(/\/+$/, "") || "/admin";
  const userMatch = path.match(/^\/admin\/users\/([^/]+)$/);
  if (userMatch) {
    const userId = decodeURIComponent(userMatch[1]);
    return {
      key: "users",
      title: "User Detail",
      render: () => renderUserDetail(userId),
    };
  }

  const routes = {
    "/admin": { key: "dashboard", title: "Dashboard", render: renderDashboard },
    "/admin/dashboard": { key: "dashboard", title: "Dashboard", render: renderDashboard },
    "/admin/users": { key: "users", title: "Users", render: renderUsers },
    "/admin/jobs": { key: "jobs", title: "Jobs", render: renderJobsAdmin },
    "/admin/usage": { key: "usage", title: "Usage", render: renderUsage },
    "/admin/quotas": { key: "quotas", title: "Quotas", render: renderQuotas },
    "/admin/security": { key: "security", title: "Security", render: renderSecurity },
    "/admin/audit": { key: "audit", title: "Audit Logs", render: renderAudit },
  };
  return routes[path] || routes["/admin"];
}

function renderAccessDenied() {
  const root = document.getElementById("admin-root");
  root.innerHTML = `
    <div class="mx-auto grid min-h-screen max-w-3xl content-center px-4">
      <section class="panel p-6">
        <p class="text-sm font-semibold uppercase text-rose-600">403</p>
        <h1 class="mt-2 text-2xl font-semibold">Access denied</h1>
        <p class="mt-2 text-sm text-slate-600">This area is available only to users with the admin role.</p>
        <div class="mt-5 flex flex-wrap gap-2">
          <a href="/" class="btn px-4 py-2 text-sm">Back to app</a>
          <button id="admin-denied-logout" class="btn px-4 py-2 text-sm">Logout</button>
        </div>
      </section>
    </div>
  `;
  document.getElementById("admin-denied-logout")?.addEventListener("click", () => {
    setToken(null);
    updateTokenStatus();
    window.history.replaceState({}, "", "/");
    renderAdminRouter();
  });
}

function handleRouteError(route, err) {
  const message = err?.message || "Request failed";
  if (/missing bearer|invalid token|user is not active/i.test(message)) {
    setToken(null);
    updateTokenStatus();
    window.history.replaceState({}, "", "/");
    renderAdminRouter();
    return;
  }
  if (/admin privileges|forbidden/i.test(message)) {
    renderAccessDenied();
    return;
  }
  renderShell(route.key, route.title, errorBlock(message));
}

function renderShell(active, title, content) {
  const root = document.getElementById("admin-root");
  const current = getCurrentUserFromToken();
  const notice = flash ? messageBlock(flash.message, flash.type) : "";
  flash = null;

  root.innerHTML = `
    <div class="mx-auto grid min-h-screen max-w-7xl gap-4 px-4 py-4 sm:px-6 lg:grid-cols-[230px_minmax(0,1fr)] lg:px-8 lg:py-6">
      <aside class="panel h-fit p-3 lg:sticky lg:top-6">
        <div class="px-2 py-2">
          <a href="/" class="text-2xl font-semibold tracking-normal text-slate-950">MediaFlow</a>
          <p class="mt-1 text-xs text-slate-500">${h(current?.username || "admin")} · admin</p>
        </div>
        <nav class="mt-3 grid gap-1">
          ${NAV.map(([href, label, key]) => `
            <a href="${href}" class="admin-nav-link ${active === key ? "active" : ""}">
              ${h(label)}
            </a>
          `).join("")}
        </nav>
        <div class="mt-4 grid gap-2 border-t border-slate-200 pt-4">
          <a href="/" class="btn px-3 py-2 text-center text-sm">User App</a>
          <button id="admin-logout" class="btn px-3 py-2 text-sm">Logout</button>
        </div>
      </aside>

      <main class="grid content-start gap-4">
        <header class="panel grid gap-3 p-4 md:grid-cols-[1fr_auto] md:items-center">
          <div>
            <h1 class="text-2xl font-semibold tracking-normal text-slate-950">${h(title)}</h1>
            <p class="mt-1 text-sm text-slate-500">Backend controlled admin operations</p>
          </div>
          <span class="rounded-full bg-slate-900 px-3 py-1 text-xs text-white">Admin</span>
        </header>
        ${notice}
        ${content}
      </main>
    </div>
  `;

  document.getElementById("admin-logout")?.addEventListener("click", () => {
    setToken(null);
    updateTokenStatus();
    window.history.replaceState({}, "", "/");
    renderAdminRouter();
  });
}

async function renderDashboard() {
  const [today, week, month, heavy, quotaEvents, jobs, blocked] = await Promise.all([
    safe(adminApi.usageSummary("today"), { summary: {} }),
    safe(adminApi.usageSummary("week"), { summary: {} }),
    safe(adminApi.usageSummary("month"), { summary: {} }),
    safe(adminApi.heavyUsers("today"), { users: [] }),
    safe(adminApi.quotaExceeded("today"), { events: [] }),
    safe(adminApi.listJobs({ limit: 100 }), []),
    safe(adminApi.blockedLogins(), { blocked: [] }),
  ]);

  const activeJobs = Array.isArray(jobs) ? jobs.filter((job) => ["queued", "running"].includes(job.status)) : [];
  const queuedJobs = activeJobs.filter((job) => job.status === "queued");
  const t = today.summary || {};
  const w = week.summary || {};
  const m = month.summary || {};

  renderShell(
    "dashboard",
    "Dashboard",
    `
      <section class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        ${metricCard("Active jobs", activeJobs.length)}
        ${metricCard("Queue size", queuedJobs.length)}
        ${metricCard("Jobs today", t.jobs_requested)}
        ${metricCard("Failed today", t.jobs_failed, "rose")}
        ${metricCard("Credits today", t.credits_used)}
        ${metricCard("Output today", formatBytes(t.total_output_bytes || 0))}
        ${metricCard("Jobs this week", w.jobs_requested)}
        ${metricCard("Jobs this month", m.jobs_requested)}
      </section>

      <section class="grid gap-4 xl:grid-cols-2">
        ${sectionPanel("Heavy users today", tableHtml(
          ["User", "Jobs", "Credits", "Output"],
          (heavy.users || []).map((row) => [
            h(row.user_id),
            num(row.jobs_requested),
            num(row.credits_used || row.credits_estimated),
            formatBytes(row.total_output_bytes || 0),
          ]),
          "No usage recorded today",
        ))}
        ${sectionPanel("Recent quota events", quotaEventsTable(quotaEvents.events || []))}
      </section>

      <section class="grid gap-4 xl:grid-cols-2">
        ${sectionPanel("Active jobs", jobsTable(activeJobs.slice(0, 8), { compact: true }))}
        ${sectionPanel("Blocked logins", blockedLoginsTable(blocked.blocked || []))}
      </section>
    `,
  );
}

async function renderUsers() {
  const params = new URLSearchParams(window.location.search);
  const filters = {
    search: params.get("search") || "",
    role: params.get("role") || "",
    status: params.get("status") || "",
    include_deleted: params.get("include_deleted") === "true",
    limit: 100,
  };
  const users = await adminApi.listUsers(filters);

  renderShell(
    "users",
    "Users",
    `
      <section class="panel p-4">
        <form id="admin-user-filters" class="grid gap-3 md:grid-cols-[minmax(0,1fr)_160px_160px_auto_auto] md:items-end">
          ${inputField("search", "Search", filters.search, "username or email")}
          ${selectField("role", "Role", filters.role, ["", ...ROLE_OPTIONS])}
          ${selectField("status", "Status", filters.status, ["", ...STATUS_OPTIONS])}
          <label class="flex min-h-10 items-center gap-2 text-sm text-slate-600">
            <input name="include_deleted" type="checkbox" class="h-4 w-4 rounded border-slate-300" ${filters.include_deleted ? "checked" : ""} />
            Deleted
          </label>
          <button class="btn-primary h-10 px-4 text-sm" type="submit">Apply</button>
        </form>
      </section>

      <section class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div class="panel overflow-hidden">
          ${usersTable(users)}
        </div>
        ${createUserPanel()}
      </section>
    `,
  );

  document.getElementById("admin-user-filters")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const query = new URLSearchParams();
    ["search", "role", "status"].forEach((field) => {
      const value = String(form.get(field) || "").trim();
      if (value) query.set(field, value);
    });
    if (form.get("include_deleted")) query.set("include_deleted", "true");
    navigate(`/admin/users${query.toString() ? `?${query}` : ""}`);
  });

  document.getElementById("admin-create-user")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = formPayload(form, ["username", "password", "email", "role", "status"]);
    if (!payload.email) payload.email = null;
    if (!payload.username || !payload.password) {
      setFlash("Username and password are required.", "error");
      renderUsers();
      return;
    }
    try {
      await adminApi.createUser(payload);
      setFlash("User created.", "success");
      renderUsers();
    } catch (err) {
      setFlash(err.message, "error");
      renderUsers();
    }
  });

  bindUserActionButtons();
}

async function renderUserDetail(userId) {
  const user = await adminApi.getUser(userId);
  const [quota, today, week, month, daily, jobs, audit] = await Promise.all([
    safe(adminApi.getUserQuota(userId), null),
    safe(adminApi.userUsage(userId, "today"), { summary: {} }),
    safe(adminApi.userUsage(userId, "week"), { summary: {} }),
    safe(adminApi.userUsage(userId, "month"), { summary: {} }),
    safe(adminApi.userDailyUsage(userId, 30), { daily: [] }),
    safe(adminApi.listJobs({ user: user.username, limit: 100 }), []),
    safe(adminApi.auditLogs({ limit: 100 }), { events: [] }),
  ]);
  const userJobs = Array.isArray(jobs) ? jobs.slice(0, 10) : [];
  const auditRows = (audit.events || [])
    .filter((event) => event.target_id === user.id || event.actor_user_id === user.id)
    .slice(0, 10);

  renderShell(
    "users",
    user.username,
    `
      <section class="grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(360px,1.1fr)]">
        ${sectionPanel("Profile", userDetailPanel(user))}
        ${sectionPanel("Edit user", editUserForm(user))}
      </section>

      <section class="grid gap-3 md:grid-cols-3">
        ${metricCard("Jobs today", today.summary?.jobs_requested)}
        ${metricCard("Credits this week", week.summary?.credits_used)}
        ${metricCard("Output this month", formatBytes(month.summary?.total_output_bytes || 0))}
      </section>

      <section class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(360px,0.95fr)]">
        ${sectionPanel("Effective quota", quota ? quotaSummary(quota) : errorBlock("Quota data unavailable"))}
        ${sectionPanel("User quota override", quota ? quotaOverrideForm(quota) : "")}
      </section>

      <section class="grid gap-4 xl:grid-cols-2">
        ${sectionPanel("Daily usage", dailyUsageTable(daily.daily || []))}
        ${sectionPanel("Recent jobs", jobsTable(userJobs, { compact: true }))}
      </section>

      ${sectionPanel("Recent audit events", auditTable(auditRows, { compact: true }))}
    `,
  );

  document.getElementById("admin-edit-user")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = formPayload(event.currentTarget, ["username", "email", "role", "status"]);
    if (!payload.email) payload.email = null;
    if (payload.role !== user.role && !window.confirm("Change this user's role?")) return;
    if (
      payload.status !== user.status &&
      payload.status !== "active" &&
      !window.confirm(`Change this user's status to ${payload.status}?`)
    ) {
      return;
    }
    try {
      await adminApi.updateUser(user.id, payload);
      setFlash("User updated.", "success");
      renderUserDetail(user.id);
    } catch (err) {
      setFlash(err.message, "error");
      renderUserDetail(user.id);
    }
  });

  document.getElementById("admin-user-quota")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = quotaPayload(event.currentTarget, true);
    try {
      await adminApi.updateUserQuota(user.id, payload);
      setFlash("User quota override saved.", "success");
      renderUserDetail(user.id);
    } catch (err) {
      setFlash(err.message, "error");
      renderUserDetail(user.id);
    }
  });

  document.getElementById("admin-clear-user-quota")?.addEventListener("click", async () => {
    if (!window.confirm("Clear this user's quota override and return to role defaults?")) return;
    try {
      await adminApi.deleteUserQuota(user.id);
      setFlash("User quota override cleared.", "success");
      renderUserDetail(user.id);
    } catch (err) {
      setFlash(err.message, "error");
      renderUserDetail(user.id);
    }
  });

  bindUserActionButtons();
}

async function renderQuotas() {
  const roles = await adminApi.listRoleQuotas();
  renderShell(
    "quotas",
    "Quotas",
    `
      <section class="grid gap-4 xl:grid-cols-2">
        ${roles.map((role) => sectionPanel(`${role.role} role`, roleQuotaForm(role))).join("")}
      </section>
      ${sectionPanel("User overrides", `
        <form id="admin-quota-user-jump" class="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
          ${inputField("user_id", "User ID", "", "paste user id")}
          <button class="btn-primary h-10 px-4 text-sm" type="submit">Open User Quota</button>
        </form>
      `)}
    `,
  );

  document.querySelectorAll("[data-role-quota-form]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const role = event.currentTarget.dataset.roleQuotaForm;
      if (!window.confirm(`Update default quota for ${role}?`)) return;
      try {
        await adminApi.updateRoleQuota(role, quotaPayload(event.currentTarget, false));
        setFlash("Role quota updated.", "success");
        renderQuotas();
      } catch (err) {
        setFlash(err.message, "error");
        renderQuotas();
      }
    });
  });

  document.getElementById("admin-quota-user-jump")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const userId = String(new FormData(event.currentTarget).get("user_id") || "").trim();
    if (userId) navigate(`/admin/users/${encodeURIComponent(userId)}`);
  });
}

async function renderUsage() {
  const range = selectedRange();
  const [summary, users, heavy, quota] = await Promise.all([
    adminApi.usageSummary(range),
    adminApi.usageUsers(range),
    adminApi.heavyUsers(range),
    adminApi.quotaExceeded(range),
  ]);
  const s = summary.summary || {};
  renderShell(
    "usage",
    "Usage",
    `
      ${rangeTabs("/admin/usage", range)}
      <section class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        ${metricCard("Jobs requested", s.jobs_requested)}
        ${metricCard("Succeeded", s.jobs_succeeded)}
        ${metricCard("Failed", s.jobs_failed, "rose")}
        ${metricCard("Credits used", s.credits_used)}
        ${metricCard("Output", formatBytes(s.total_output_bytes || 0))}
        ${metricCard("Avg processing", formatMs(s.avg_processing_ms))}
        ${metricCard("Playlist items", s.playlist_items_requested)}
        ${metricCard("Canceled", s.jobs_canceled)}
      </section>
      <section class="grid gap-4 xl:grid-cols-2">
        ${sectionPanel("Usage by user", usageUsersTable(users.users || []))}
        ${sectionPanel("Heavy users", usageUsersTable(heavy.users || []))}
      </section>
      ${sectionPanel("Quota exceeded", quotaEventsTable(quota.events || []))}
    `,
  );
}

async function renderJobsAdmin() {
  const params = new URLSearchParams(window.location.search);
  const filters = {
    user: params.get("user") || "",
    status: params.get("status") || "",
    limit: 100,
  };
  const jobs = await adminApi.listJobs(filters);

  renderShell(
    "jobs",
    "Jobs",
    `
      <section class="panel p-4">
        <form id="admin-job-filters" class="grid gap-3 md:grid-cols-[minmax(0,1fr)_180px_auto] md:items-end">
          ${inputField("user", "User", filters.user, "username")}
          ${selectField("status", "Status", filters.status, ["", "queued", "running", "succeeded", "failed", "canceled"])}
          <button class="btn-primary h-10 px-4 text-sm" type="submit">Apply</button>
        </form>
      </section>
      <section class="panel overflow-hidden">
        ${jobsTable(jobs, { adminActions: true })}
      </section>
    `,
  );

  document.getElementById("admin-job-filters")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const query = new URLSearchParams();
    ["user", "status"].forEach((field) => {
      const value = String(form.get(field) || "").trim();
      if (value) query.set(field, value);
    });
    navigate(`/admin/jobs${query.toString() ? `?${query}` : ""}`);
  });

  document.querySelectorAll("[data-cancel-job]").forEach((button) => {
    button.addEventListener("click", async () => {
      const jobId = button.dataset.cancelJob;
      if (!window.confirm(`Cancel job ${shortJobId(jobId)}?`)) return;
      try {
        await adminApi.cancelJob(jobId);
        setFlash("Cancel requested.", "success");
        renderJobsAdmin();
      } catch (err) {
        setFlash(err.message, "error");
        renderJobsAdmin();
      }
    });
  });
}

async function renderSecurity() {
  const [attempts, blocked] = await Promise.all([
    adminApi.loginAttempts({ limit: 100 }),
    adminApi.blockedLogins(),
  ]);
  renderShell(
    "security",
    "Security",
    `
      <section class="grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(360px,0.7fr)]">
        ${sectionPanel("Login attempts", loginAttemptsTable(attempts.attempts || []))}
        ${sectionPanel("Blocked logins", blockedLoginsTable(blocked.blocked || []))}
      </section>
    `,
  );
}

async function renderAudit() {
  const audit = await adminApi.auditLogs({ limit: 150 });
  renderShell("audit", "Audit Logs", sectionPanel("Events", auditTable(audit.events || [])));
}

function usersTable(users) {
  if (!users.length) return emptyState("No users found");
  return `
    <div class="overflow-auto">
      <table class="admin-table">
        <thead>
          <tr>
            <th>Username</th><th>Email</th><th>Role</th><th>Status</th><th>Last login</th><th>Created</th><th>Token</th><th>Actions</th>
          </tr>
        </thead>
        <tbody>
          ${users.map((user) => `
            <tr>
              <td><a href="/admin/users/${encodeURIComponent(user.id)}" class="font-semibold text-slate-950 hover:text-emerald-700">${h(user.username)}</a></td>
              <td>${h(user.email || "--")}</td>
              <td>${roleBadge(user.role)}</td>
              <td>${statusBadge(user.status)}</td>
              <td>${timestampHtml(user.last_login_at)}</td>
              <td>${timestampHtml(user.created_at)}</td>
              <td>${num(user.token_version)}</td>
              <td>
                <div class="flex min-w-[300px] flex-wrap gap-2">
                  <button class="btn px-2 py-1 text-xs" data-user-action="view" data-user-id="${h(user.id)}">View</button>
                  ${user.status === "active"
                    ? `<button class="btn danger-soft px-2 py-1 text-xs" data-user-action="disable" data-user-id="${h(user.id)}">Disable</button>`
                    : `<button class="btn px-2 py-1 text-xs" data-user-action="enable" data-user-id="${h(user.id)}">Enable</button>`}
                  <button class="btn px-2 py-1 text-xs" data-user-action="reset" data-user-id="${h(user.id)}">Reset</button>
                  <button class="btn px-2 py-1 text-xs" data-user-action="revoke" data-user-id="${h(user.id)}">Revoke</button>
                  <button class="btn danger-soft px-2 py-1 text-xs" data-user-action="delete" data-user-id="${h(user.id)}">Delete</button>
                </div>
              </td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function createUserPanel() {
  return `
    <section class="panel p-4">
      <h2 class="text-lg font-semibold">Create User</h2>
      <form id="admin-create-user" class="mt-4 grid gap-3">
        ${inputField("username", "Username")}
        ${inputField("email", "Email", "", "optional")}
        ${inputField("password", "Password", "", "", "password")}
        ${selectField("role", "Role", "user", ROLE_OPTIONS)}
        ${selectField("status", "Status", "active", ["active", "disabled", "locked"])}
        <button class="btn-primary h-10 px-4 text-sm" type="submit">Create User</button>
      </form>
    </section>
  `;
}

function userDetailPanel(user) {
  return `
    <div class="grid gap-3 text-sm">
      ${detailRow("ID", user.id)}
      ${detailRow("Username", user.username)}
      ${detailRow("Email", user.email || "--")}
      ${detailRow("Role", roleBadge(user.role))}
      ${detailRow("Status", statusBadge(user.status))}
      ${detailRow("Token version", user.token_version)}
      ${detailRow("Created", timestampHtml(user.created_at))}
      ${detailRow("Updated", timestampHtml(user.updated_at))}
      ${detailRow("Last login", timestampHtml(user.last_login_at))}
      ${detailRow("Deleted", timestampHtml(user.deleted_at))}
      <div class="mt-2 flex flex-wrap gap-2">
        <button class="btn danger-soft px-3 py-2 text-sm" data-user-action="disable" data-user-id="${h(user.id)}">Disable</button>
        <button class="btn px-3 py-2 text-sm" data-user-action="enable" data-user-id="${h(user.id)}">Enable</button>
        <button class="btn danger-soft px-3 py-2 text-sm" data-user-action="delete" data-user-id="${h(user.id)}">Soft delete</button>
        <button class="btn px-3 py-2 text-sm" data-user-action="reset" data-user-id="${h(user.id)}">Reset password</button>
        <button class="btn px-3 py-2 text-sm" data-user-action="revoke" data-user-id="${h(user.id)}">Revoke tokens</button>
      </div>
    </div>
  `;
}

function editUserForm(user) {
  return `
    <form id="admin-edit-user" class="grid gap-3">
      ${inputField("username", "Username", user.username)}
      ${inputField("email", "Email", user.email || "")}
      ${selectField("role", "Role", user.role, ROLE_OPTIONS)}
      ${selectField("status", "Status", user.status, STATUS_OPTIONS)}
      <button class="btn-primary h-10 px-4 text-sm" type="submit">Save Changes</button>
    </form>
  `;
}

function roleQuotaForm(row) {
  return `
    <form data-role-quota-form="${h(row.role)}" class="grid gap-3">
      ${quotaInputs(row.quota, false)}
      <button class="btn-primary h-10 px-4 text-sm" type="submit">Save ${h(row.role)} quota</button>
    </form>
  `;
}

function quotaOverrideForm(quota) {
  return `
    <form id="admin-user-quota" class="grid gap-3">
      ${quotaInputs(quota.override_quota || {}, true)}
      <div class="flex flex-wrap gap-2">
        <button class="btn-primary h-10 px-4 text-sm" type="submit">Save Override</button>
        <button id="admin-clear-user-quota" class="btn h-10 px-4 text-sm" type="button">Clear Override</button>
      </div>
    </form>
  `;
}

function quotaSummary(quota) {
  const effective = quota.effective_quota || {};
  const override = quota.override_quota || {};
  return `
    <div class="grid gap-2 text-sm">
      ${QUOTA_FIELDS.map(([field, label]) => `
        <div class="grid grid-cols-[minmax(0,1fr)_auto_auto] gap-3 border-b border-slate-100 py-2">
          <span class="text-slate-500">${h(label)}</span>
          <span class="font-semibold text-slate-950">${h(formatQuotaValue(effective[field]))}</span>
          <span class="text-xs text-slate-400">${override[field] == null ? "role" : "override"}</span>
        </div>
      `).join("")}
    </div>
  `;
}

function quotaInputs(values, allowNull) {
  return `
    <div class="grid gap-3 sm:grid-cols-2">
      ${QUOTA_FIELDS.map(([field, label]) => {
        if (field === "max_video_quality") {
          return selectField(field, label, values[field] ?? "", allowNull ? ["", ...QUALITY_OPTIONS] : QUALITY_OPTIONS);
        }
        return inputField(field, label, values[field] ?? "", allowNull ? "fallback" : "", "number");
      }).join("")}
    </div>
  `;
}

function jobsTable(jobs, options = {}) {
  if (!jobs.length) return emptyState("No jobs found");
  return `
    <div class="overflow-auto">
      <table class="admin-table">
        <thead>
          <tr>
            <th>Job</th><th>User</th><th>Status</th><th>Mode</th><th>Quality</th><th>Playlist</th><th>Progress</th><th>Created</th><th>Error</th>${options.adminActions ? "<th>Actions</th>" : ""}
          </tr>
        </thead>
        <tbody>
          ${jobs.map((job) => `
            <tr>
              <td class="font-mono text-xs">${h(shortJobId(job.job_id))}</td>
              <td>${h(job.user)}</td>
              <td>${statusBadge(job.status)}</td>
              <td>${h(job.mode)}</td>
              <td>${h(job.quality)}</td>
              <td>${job.playlist_total ? num(job.playlist_total) : "--"}</td>
              <td>
                <div class="min-w-28">
                  <div class="h-2 overflow-hidden rounded-full bg-slate-200">
                    <div class="h-2 rounded-full bg-emerald-500" style="width:${clampPercent(job.progress_percent)}%"></div>
                  </div>
                  <div class="mt-1 text-xs text-slate-500">${clampPercent(job.progress_percent)}%</div>
                </div>
              </td>
              <td>${timestampHtml(job.created_at)}</td>
              <td>${h(job.error_code || "--")}</td>
              ${options.adminActions ? `<td>${["queued", "running"].includes(job.status) ? `<button class="btn danger-soft px-2 py-1 text-xs" data-cancel-job="${h(job.job_id)}">Cancel</button>` : "--"}</td>` : ""}
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function usageUsersTable(rows) {
  return tableHtml(
    ["User", "Jobs", "Credits used", "Credits est.", "Output"],
    rows.map((row) => [
      h(row.user_id),
      num(row.jobs_requested),
      num(row.credits_used),
      num(row.credits_estimated),
      formatBytes(row.total_output_bytes || 0),
    ]),
    "No usage rows",
  );
}

function quotaEventsTable(events) {
  return tableHtml(
    ["Time", "User", "Reason", "Mode", "Quality"],
    events.map((event) => [
      timestampHtml(event.created_at),
      h(event.user_id),
      h(event.error_code || "--"),
      h(event.mode || "--"),
      h(event.quality || "--"),
    ]),
    "No quota events",
  );
}

function dailyUsageTable(rows) {
  return tableHtml(
    ["Date", "Jobs", "Succeeded", "Failed", "Credits", "Output"],
    rows.map((row) => [
      h(row.date),
      num(row.jobs_requested),
      num(row.jobs_succeeded),
      num(row.jobs_failed),
      num(row.credits_used),
      formatBytes(row.total_output_bytes || 0),
    ]),
    "No daily usage rows",
  );
}

function loginAttemptsTable(rows) {
  return tableHtml(
    ["Time", "Username", "Result", "Reason", "IP hash", "User agent"],
    rows.map((row) => [
      timestampHtml(row.created_at),
      h(row.username || "--"),
      row.success ? statusBadge("success") : statusBadge("failed"),
      h(row.failure_reason || "--"),
      h(row.ip_hash || "--"),
      h(row.user_agent || "--"),
    ]),
    "No login attempts",
  );
}

function blockedLoginsTable(rows) {
  return tableHtml(
    ["Username", "IP hash", "Failed", "Last attempt"],
    rows.map((row) => [
      h(row.username || "--"),
      h(row.ip_hash || "--"),
      num(row.failed_attempts),
      timestampHtml(row.last_attempt_at),
    ]),
    "No blocked logins",
  );
}

function auditTable(rows, options = {}) {
  if (!rows.length) return emptyState("No audit events");
  return `
    <div class="overflow-auto">
      <table class="admin-table">
        <thead>
          <tr><th>Time</th><th>Actor</th><th>Action</th><th>Target</th><th>Metadata</th></tr>
        </thead>
        <tbody>
          ${rows.map((row) => `
            <tr>
              <td>${timestampHtml(row.created_at)}</td>
              <td class="font-mono text-xs">${h(row.actor_user_id || "--")}</td>
              <td>${h(row.action)}</td>
              <td>${h(row.target_type)} · <span class="font-mono text-xs">${h(row.target_id)}</span></td>
              <td>
                <details class="${options.compact ? "max-w-md" : ""}">
                  <summary class="cursor-pointer text-xs font-semibold text-slate-600">View</summary>
                  <pre class="mt-2 max-h-60 overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-100">${h(prettyJson(row.metadata_json))}</pre>
                </details>
              </td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function bindUserActionButtons() {
  document.querySelectorAll("[data-user-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const action = button.dataset.userAction;
      const userId = button.dataset.userId;
      if (action === "view") {
        navigate(`/admin/users/${encodeURIComponent(userId)}`);
        return;
      }
      try {
        if (action === "disable") {
          if (!window.confirm("Disable this user and invalidate current tokens?")) return;
          await adminApi.disableUser(userId);
          setFlash("User disabled.", "success");
        } else if (action === "enable") {
          await adminApi.enableUser(userId);
          setFlash("User enabled.", "success");
        } else if (action === "delete") {
          if (!window.confirm("Soft delete this user? Existing jobs and audit rows stay in the database.")) return;
          await adminApi.softDeleteUser(userId);
          setFlash("User soft-deleted.", "success");
        } else if (action === "reset") {
          openResetPasswordDialog(userId);
          return;
        } else if (action === "revoke") {
          if (!window.confirm("Revoke all current access tokens for this user?")) return;
          await adminApi.revokeTokens(userId);
          setFlash("Tokens revoked.", "success");
        }
        renderAdminRouter();
      } catch (err) {
        setFlash(err.message, "error");
        renderAdminRouter();
      }
    });
  });
}

function openResetPasswordDialog(userId) {
  document.getElementById("admin-modal")?.remove();
  document.body.insertAdjacentHTML(
    "beforeend",
    `
      <div id="admin-modal" class="fixed inset-0 z-50 grid place-items-center bg-slate-950/45 px-4">
        <form id="admin-reset-password-form" class="panel w-full max-w-md p-5">
          <h2 class="text-lg font-semibold text-slate-950">Reset password</h2>
          <div class="mt-4 grid gap-3">
            ${inputField("new_password", "New password", "", "", "password")}
            ${inputField("confirm_password", "Confirm password", "", "", "password")}
          </div>
          <div class="mt-5 flex flex-wrap justify-end gap-2">
            <button id="admin-modal-cancel" class="btn px-4 py-2 text-sm" type="button">Cancel</button>
            <button class="btn-primary px-4 py-2 text-sm" type="submit">Reset Password</button>
          </div>
        </form>
      </div>
    `,
  );

  const modal = document.getElementById("admin-modal");
  const form = document.getElementById("admin-reset-password-form");
  const close = () => modal?.remove();
  document.getElementById("admin-modal-cancel")?.addEventListener("click", close);
  modal?.addEventListener("click", (event) => {
    if (event.target === modal) close();
  });
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const password = String(data.get("new_password") || "");
    const confirmation = String(data.get("confirm_password") || "");
    if (!password || password !== confirmation) {
      setFlash("Password confirmation does not match.", "error");
      close();
      renderAdminRouter();
      return;
    }
    form.reset();
    try {
      await adminApi.resetPassword(userId, password);
      setFlash("Password reset.", "success");
    } catch (err) {
      setFlash(err.message, "error");
    } finally {
      close();
      renderAdminRouter();
    }
  });
}

function rangeTabs(basePath, active) {
  return `
    <div class="panel flex flex-wrap gap-2 p-3">
      ${RANGE_OPTIONS.map((range) => `
        <a href="${basePath}?range=${range}" class="btn px-3 py-2 text-sm ${active === range ? "ring-2 ring-emerald-300" : ""}">${h(range)}</a>
      `).join("")}
    </div>
  `;
}

function selectedRange() {
  const value = new URLSearchParams(window.location.search).get("range") || "today";
  return RANGE_OPTIONS.includes(value) ? value : "today";
}

function sectionPanel(title, body) {
  return `
    <section class="panel p-4">
      <h2 class="text-lg font-semibold text-slate-950">${h(title)}</h2>
      <div class="mt-4">${body}</div>
    </section>
  `;
}

function metricCard(label, value, tone = "default") {
  const color = tone === "rose" ? "text-rose-700 bg-rose-50" : "text-slate-950 bg-white/70";
  return `
    <div class="panel p-4">
      <p class="text-xs font-semibold uppercase text-slate-500">${h(label)}</p>
      <p class="mt-2 rounded-lg px-3 py-2 text-2xl font-semibold ${color}">${h(formatMetric(value))}</p>
    </div>
  `;
}

function tableHtml(headers, rows, empty) {
  if (!rows.length) return emptyState(empty);
  return `
    <div class="overflow-auto">
      <table class="admin-table">
        <thead><tr>${headers.map((header) => `<th>${h(header)}</th>`).join("")}</tr></thead>
        <tbody>
          ${rows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function inputField(name, label, value = "", placeholder = "", type = "text") {
  return `
    <label class="grid gap-1 text-sm">
      <span class="font-medium text-slate-700">${h(label)}</span>
      <input
        name="${h(name)}"
        type="${h(type)}"
        value="${h(value)}"
        placeholder="${h(placeholder)}"
        class="admin-input"
      />
    </label>
  `;
}

function selectField(name, label, value, options) {
  return `
    <label class="grid gap-1 text-sm">
      <span class="font-medium text-slate-700">${h(label)}</span>
      <select name="${h(name)}" class="admin-input">
        ${options.map((option) => `
          <option value="${h(option)}" ${String(value || "") === String(option) ? "selected" : ""}>${option ? h(option) : "Any"}</option>
        `).join("")}
      </select>
    </label>
  `;
}

function detailRow(label, value) {
  return `
    <div class="grid gap-1 border-b border-slate-100 pb-2 sm:grid-cols-[150px_minmax(0,1fr)]">
      <span class="text-slate-500">${h(label)}</span>
      <span class="min-w-0 break-words text-slate-900">${typeof value === "string" && value.startsWith("<") ? value : h(value)}</span>
    </div>
  `;
}

function roleBadge(role) {
  const cls = role === "admin" ? "bg-blue-50 text-blue-700" : "bg-slate-100 text-slate-700";
  return `<span class="admin-badge ${cls}">${h(role || "--")}</span>`;
}

function statusBadge(status) {
  const tones = {
    active: "bg-emerald-50 text-emerald-700",
    success: "bg-emerald-50 text-emerald-700",
    succeeded: "bg-emerald-50 text-emerald-700",
    running: "bg-blue-50 text-blue-700",
    queued: "bg-amber-50 text-amber-700",
    disabled: "bg-slate-100 text-slate-700",
    locked: "bg-orange-50 text-orange-700",
    deleted: "bg-rose-50 text-rose-700",
    failed: "bg-rose-50 text-rose-700",
    canceled: "bg-slate-100 text-slate-700",
  };
  return `<span class="admin-badge ${tones[status] || "bg-slate-100 text-slate-700"}">${h(status || "--")}</span>`;
}

function messageBlock(message, type = "info") {
  const cls = type === "error" ? "border-rose-200 bg-rose-50 text-rose-700" : type === "success" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-white/80 text-slate-700";
  return `<div class="rounded-lg border px-4 py-3 text-sm ${cls}">${h(message)}</div>`;
}

function errorBlock(message) {
  return messageBlock(message, "error");
}

function loadingBlock(label) {
  return `
    <section class="panel p-5">
      <div class="flex items-center gap-3 text-sm text-slate-600">
        <span class="busy-dot h-2.5 w-2.5 rounded-full bg-emerald-500"></span>
        <span>${h(label)}</span>
      </div>
    </section>
  `;
}

function emptyState(text) {
  return `<div class="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">${h(text)}</div>`;
}

function formPayload(form, fields) {
  const data = new FormData(form);
  const payload = {};
  fields.forEach((field) => {
    payload[field] = String(data.get(field) || "").trim();
  });
  return payload;
}

function quotaPayload(form, allowNull) {
  const data = new FormData(form);
  const payload = {};
  QUOTA_FIELDS.forEach(([field]) => {
    const raw = String(data.get(field) ?? "").trim();
    if (!raw) {
      if (allowNull) payload[field] = null;
      return;
    }
    payload[field] = field === "max_video_quality" ? raw : Number(raw);
  });
  return payload;
}

function setFlash(message, type = "info") {
  flash = { message, type };
}

async function safe(promise, fallback) {
  try {
    return await promise;
  } catch {
    return fallback;
  }
}

function prettyJson(value) {
  if (!value) return "{}";
  try {
    return JSON.stringify(JSON.parse(value), null, 2);
  } catch {
    return String(value);
  }
}

function formatMetric(value) {
  if (value === undefined || value === null || value === "") return "0";
  return String(value);
}

function formatQuotaValue(value) {
  if (value === undefined || value === null || value === "") return "--";
  return value;
}

function formatMs(ms) {
  const value = Number(ms || 0);
  if (!value) return "--";
  if (value < 1000) return `${value} ms`;
  return `${(value / 1000).toFixed(value >= 10000 ? 0 : 1)} s`;
}

function num(value) {
  return h(Number(value || 0).toLocaleString());
}

function h(value) {
  return escapeHtml(String(value ?? ""));
}
