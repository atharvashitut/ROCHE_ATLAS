const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

export const api = {
  triageVision: (image_base64) => request('/triage/vision', { method: 'POST', body: JSON.stringify({ image_base64 }) }),
  incidentRelationships: (ticketId) => request(`/triage/incidents/${encodeURIComponent(ticketId)}/relationships`),
  assessChange: (payload) => request('/changes', { method: 'POST', body: JSON.stringify(payload) }),
  listAudit: () => request('/audit'),
  recordAudit: (payload) => request('/audit', { method: 'POST', body: JSON.stringify(payload) }),
  generatePlaybook: (payload) => request('/audit/playbook', { method: 'POST', body: JSON.stringify(payload) }),
  rca: (payload) => request('/predictive/rca', { method: 'POST', body: JSON.stringify(payload) }),
  createProblem: (payload) => request('/predictive/problem', { method: 'POST', body: JSON.stringify(payload) }),
  detectDrift: (payload) => request('/predictive/drift', { method: 'POST', body: JSON.stringify(payload) }),
}

export async function asBase64(file) {
  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
  return dataUrl.split(',')[1]
}
