import { api } from "../api/client.js";

function withQuery(path, params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    query.set(key, String(value));
  });
  const suffix = query.toString();
  return suffix ? `${path}?${suffix}` : path;
}

function jsonOptions(method, body) {
  return {
    method,
    body: JSON.stringify(body),
  };
}

export const adminApi = {
  listUsers(params) {
    return api(withQuery("/admin/users", params));
  },
  createUser(payload) {
    return api("/admin/users", jsonOptions("POST", payload));
  },
  getUser(userId) {
    return api(`/admin/users/${encodeURIComponent(userId)}`);
  },
  updateUser(userId, payload) {
    return api(`/admin/users/${encodeURIComponent(userId)}`, jsonOptions("PATCH", payload));
  },
  disableUser(userId) {
    return api(`/admin/users/${encodeURIComponent(userId)}/disable`, { method: "POST" });
  },
  enableUser(userId) {
    return api(`/admin/users/${encodeURIComponent(userId)}/enable`, { method: "POST" });
  },
  softDeleteUser(userId) {
    return api(`/admin/users/${encodeURIComponent(userId)}/soft-delete`, { method: "POST" });
  },
  resetPassword(userId, newPassword) {
    return api(
      `/admin/users/${encodeURIComponent(userId)}/reset-password`,
      jsonOptions("POST", { new_password: newPassword }),
    );
  },
  revokeTokens(userId) {
    return api(`/admin/users/${encodeURIComponent(userId)}/revoke-tokens`, { method: "POST" });
  },
  listRoleQuotas() {
    return api("/admin/quotas/roles");
  },
  getRoleQuota(role) {
    return api(`/admin/quotas/roles/${encodeURIComponent(role)}`);
  },
  updateRoleQuota(role, payload) {
    return api(`/admin/quotas/roles/${encodeURIComponent(role)}`, jsonOptions("PATCH", payload));
  },
  getUserQuota(userId) {
    return api(`/admin/users/${encodeURIComponent(userId)}/quota`);
  },
  updateUserQuota(userId, payload) {
    return api(`/admin/users/${encodeURIComponent(userId)}/quota`, jsonOptions("PATCH", payload));
  },
  deleteUserQuota(userId) {
    return api(`/admin/users/${encodeURIComponent(userId)}/quota`, { method: "DELETE" });
  },
  usageSummary(range) {
    return api(withQuery("/admin/usage/summary", { range }));
  },
  usageUsers(range) {
    return api(withQuery("/admin/usage/users", { range }));
  },
  userUsage(userId, range) {
    return api(withQuery(`/admin/usage/users/${encodeURIComponent(userId)}`, { range }));
  },
  userDailyUsage(userId, days = 30) {
    return api(withQuery(`/admin/usage/users/${encodeURIComponent(userId)}/daily`, { days }));
  },
  heavyUsers(range) {
    return api(withQuery("/admin/usage/heavy-users", { range }));
  },
  quotaExceeded(range) {
    return api(withQuery("/admin/usage/quota-exceeded", { range }));
  },
  listJobs(params) {
    return api(withQuery("/admin/jobs", params));
  },
  getJob(jobId) {
    return api(`/admin/jobs/${encodeURIComponent(jobId)}`);
  },
  cancelJob(jobId) {
    return api(`/admin/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
  },
  loginAttempts(params) {
    return api(withQuery("/admin/security/login-attempts", params));
  },
  blockedLogins(params) {
    return api(withQuery("/admin/security/blocked-logins", params));
  },
  auditLogs(params) {
    return api(withQuery("/admin/security/audit-logs", params));
  },
};
