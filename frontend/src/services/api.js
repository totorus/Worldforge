const API_BASE = "/api";

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail || `API error: ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

export async function apiFetch(path, options = {}) {
  const token = localStorage.getItem("token");
  const headers = {
    "Content-Type": "application/json",
    ...(token && { Authorization: `Bearer ${token}` }),
    ...options.headers,
  };

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (response.status === 401) {
    // Try refresh
    const refreshed = await tryRefresh();
    if (refreshed) {
      headers.Authorization = `Bearer ${localStorage.getItem("token")}`;
      const retry = await fetch(`${API_BASE}${path}`, { ...options, headers });
      if (!retry.ok) {
        const data = await retry.json().catch(() => ({}));
        throw new ApiError(retry.status, data.detail);
      }
      return retry.json();
    }
    localStorage.removeItem("token");
    localStorage.removeItem("refresh_token");
    throw new ApiError(401, "Session expirée");
  }

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new ApiError(response.status, data.detail);
  }

  return response.json();
}

async function tryRefresh() {
  const refreshToken = localStorage.getItem("refresh_token");
  if (!refreshToken) return false;
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    localStorage.setItem("token", data.access_token);
    localStorage.setItem("refresh_token", data.refresh_token);
    return true;
  } catch {
    return false;
  }
}

// Auth
export const auth = {
  login: (email, password) =>
    apiFetch("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  register: (email, password) =>
    apiFetch("/auth/register", { method: "POST", body: JSON.stringify({ email, password }) }),
  me: () => apiFetch("/auth/me"),
};

// Worlds
export const worlds = {
  list: () => apiFetch("/worlds/"),
  get: (id) => apiFetch(`/worlds/${id}`),
  updateConfig: (id, config) =>
    apiFetch(`/worlds/${id}/config`, { method: "PUT", body: JSON.stringify({ config }) }),
  delete: (id) => apiFetch(`/worlds/${id}`, { method: "DELETE" }),
  getTimeline: (id) => apiFetch(`/worlds/${id}/timeline`),
  getNarrative: (id) => apiFetch(`/worlds/${id}/narrative`),
  regenerate: (id) => apiFetch(`/worlds/${id}/regenerate`, { method: "POST" }),
};

// Wizard
export const wizard = {
  start: () => apiFetch("/wizard/start", { method: "POST" }),
  sendMessage: (sessionId, content) =>
    apiFetch(`/wizard/${sessionId}/message`, { method: "POST", body: JSON.stringify({ content }) }),
  getHistory: (sessionId) => apiFetch(`/wizard/${sessionId}/history`),
  finalize: (sessionId) => apiFetch(`/wizard/${sessionId}/finalize`, { method: "POST" }),
  validate: (sessionId) => apiFetch(`/wizard/${sessionId}/validate`, { method: "POST" }),
  generate: (sessionId) => apiFetch(`/wizard/${sessionId}/generate`, { method: "POST" }),
};

// Simulate
export const simulate = {
  run: (worldId) => apiFetch(`/simulate/${worldId}`, { method: "POST" }),
  extend: (worldId, years) =>
    apiFetch(`/simulate/${worldId}/extend`, {
      method: "POST",
      body: JSON.stringify({ additional_years: years }),
    }),
  status: (worldId) => apiFetch(`/simulate/${worldId}/status`),
};

// Narrate
export const narrate = {
  run: (worldId) => apiFetch(`/narrate/${worldId}`, { method: "POST" }),
  partial: (worldId, steps) =>
    apiFetch(`/narrate/${worldId}/partial`, { method: "POST", body: JSON.stringify({ steps }) }),
  status: (worldId) => apiFetch(`/narrate/${worldId}/status`),
  blocks: (worldId) => apiFetch(`/narrate/${worldId}/blocks`),
};

// Export
export const exportApi = {
  toBookstack: (worldId) => apiFetch(`/export/${worldId}/bookstack`, { method: "POST" }),
  status: (worldId) => apiFetch(`/export/${worldId}/bookstack/status`),
  sync: (worldId) => apiFetch(`/export/${worldId}/bookstack/sync`, { method: "POST" }),
};
