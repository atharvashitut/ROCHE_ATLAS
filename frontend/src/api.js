const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: { 'Content-Type': 'application/json', ...options.headers },
      ...options,
    })
  } catch (error) {
    throw new Error(error instanceof Error ? `Unable to reach ATLAS: ${error.message}` : 'Unable to reach ATLAS.')
  }

  // An API gateway may legitimately return 204 or an empty successful body.
  // Normalising that case here keeps it out of React render paths.
  const rawBody = response.status === 204 ? '' : await response.text().catch(() => '')
  let body = {}
  if (rawBody.trim()) {
    try {
      body = JSON.parse(rawBody)
    } catch {
      if (!response.ok) throw new Error(`Request failed with status ${response.status}`)
    }
  }
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed with status ${response.status}`)
  }
  return body && typeof body === 'object' ? body : {}
}

export async function fetchDashboardTickets(assignee) {
  const params = assignee ? `?assignee=${encodeURIComponent(assignee)}` : ''
  const response = await request(`/dashboard/tickets${params}`)
  return {
    ...response,
    tickets: Array.isArray(response?.tickets) ? response.tickets : (Array.isArray(response?.data?.tickets) ? response.data.tickets : []),
  }
}

export async function fetchAssignmentGroups() {
  const response = await request('/dashboard/assignment-groups')
  return {
    ...response,
    assignment_groups: Array.isArray(response?.assignment_groups) ? response.assignment_groups : (Array.isArray(response?.data?.assignment_groups) ? response.data.assignment_groups : []),
    default_my_team_groups: Array.isArray(response?.default_my_team_groups) ? response.default_my_team_groups : [],
  }
}

export async function fetchDashboardStats({ assignmentGroups = [], assignees = [], groupFilterActive = false, startDate, endDate } = {}) {
  const params = new URLSearchParams()
  assignmentGroups.forEach((group) => params.append('assignment_group', group))
  assignees.forEach((assignee) => params.append('assignee', assignee))
  if (groupFilterActive) params.set('group_filter_active', 'true')
  if (startDate) params.set('start_date', startDate)
  if (endDate) params.set('end_date', endDate)
  const query = params.toString()
  return request(`/dashboard/stats${query ? `?${query}` : ''}`)
}

export async function fetchTicket(ticketId) {
  const response = await request(`/tickets/${encodeURIComponent(ticketId)}`)
  return { ...response, ticket: response?.ticket ?? response?.data?.ticket ?? null }
}

export async function queryCopilot({ message, ticketId, action = 'chat', history = [] }) {
  const response = await request('/chat/query', {
    method: 'POST',
    body: JSON.stringify({ message, ticket_id: ticketId || undefined, action, history: Array.isArray(history) ? history : [] }),
  })
  return {
    ...response,
    response: typeof response?.response === 'string' ? response.response : '',
    chart_data: response?.chart_data ?? null,
  }
}

export async function streamCopilot({ message, ticketId, action = 'chat', history = [], onEvent, signal } = {}) {
  let response
  try {
    response = await fetch(`${API_BASE}/chat/stream`, {
      method: 'POST',
      signal,
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({ message, ticket_id: ticketId || undefined, action, history: Array.isArray(history) ? history : [] }),
    })
  } catch (error) {
    throw new Error(error instanceof Error ? `Unable to reach ATLAS: ${error.message}` : 'Unable to reach ATLAS.')
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body?.detail || `Request failed with status ${response.status}`)
  }
  if (!response.body) throw new Error('ATLAS did not provide a readable response stream.')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let eventName = 'message'
  let dataLines = []

  const dispatchEvent = () => {
    if (!dataLines.length) return
    const rawData = dataLines.join('\n')
    dataLines = []
    try {
      const payload = JSON.parse(rawData)
      onEvent?.({ event: eventName, payload })
    } catch {
      onEvent?.({ event: 'error', payload: { message: 'ATLAS returned an invalid stream event.' } })
    }
    eventName = 'message'
  }

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    const lines = buffer.split(/\r?\n/)
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      if (!line) {
        dispatchEvent()
      } else if (line.startsWith('event:')) {
        eventName = line.slice(6).trim() || 'message'
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trimStart())
      }
      // SSE comments (": ...") intentionally keep the proxy connection
      // alive and require no client-side state update.
    }
    if (done) break
  }
  if (buffer) {
    const line = buffer.trim()
    if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
  }
  dispatchEvent()
}
