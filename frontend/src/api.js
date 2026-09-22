const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed with status ${response.status}`)
  }
  return body
}

export async function fetchDashboardTickets(assignee) {
  const params = assignee ? `?assignee=${encodeURIComponent(assignee)}` : ''
  return request(`/dashboard/tickets${params}`)
}

export async function fetchAssignmentGroups() {
  return request('/dashboard/assignment-groups')
}

export async function fetchTicket(ticketId) {
  return request(`/tickets/${encodeURIComponent(ticketId)}`)
}

export async function queryCopilot({ message, ticketId, action = 'chat' }) {
  return request('/chat/query', {
    method: 'POST',
    body: JSON.stringify({ message, ticket_id: ticketId || undefined, action }),
  })
}
