const BASE = import.meta.env.VITE_API_BASE || ''

async function get(path) {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    throw new Error(`${path} -> HTTP ${res.status}`)
  }
  return res.json()
}

export const api = {
  overview: () => get('/api/kpis/overview'),
  daily: (dimension = 'project', days = 30) =>
    get(`/api/kpis/daily?dimension=${dimension}&days=${days}`),
  top: (dimension = 'user', metric = 'cost', days = 30, limit = 10) =>
    get(`/api/kpis/top?dimension=${dimension}&metric=${metric}&days=${days}&limit=${limit}`),
  efficiency: () => get('/api/kpis/efficiency'),
  governance: () => get('/api/kpis/governance'),
  behaviour: () => get('/api/kpis/behaviour'),
  targets: () => get('/api/kpis/targets'),
  sessions: (days = 30, limit = 20) =>
    get(`/api/kpis/sessions?days=${days}&limit=${limit}`),
  anomalies: (days = 30, threshold = 1.5) =>
    get(`/api/kpis/anomalies?days=${days}&threshold=${threshold}`),
  quality: (threshold = 0.5) =>
    get(`/api/kpis/quality?threshold=${threshold}`),
  modelDaily: (days = 30, model = null) =>
    get(`/api/kpis/model-daily?days=${days}${model ? `&model=${encodeURIComponent(model)}` : ''}`),
  hourly: (days = 7) => get(`/api/kpis/hourly?days=${days}`),
  burndown: () => get('/api/kpis/burndown'),
  cohort: (days = 90) => get(`/api/kpis/cohort?days=${days}`),
}
