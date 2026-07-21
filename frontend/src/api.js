const API_URL = import.meta.env.VITE_API_URL

async function request(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(body.message || `Request failed (${response.status})`)
  }
  return body
}

export const api = {
  sendCode: (email) => request('/auth/send-code', { method: 'POST', body: JSON.stringify({ email }) }),
  verifyCode: (email, code, deviceFingerprint) =>
    request('/auth/verify-code', { method: 'POST', body: JSON.stringify({ email, code, deviceFingerprint }) }),
  checkDevice: (deviceFingerprint) =>
    request('/auth/check-device', { method: 'POST', body: JSON.stringify({ deviceFingerprint }) }),
  logout: (email, deviceFingerprint) =>
    request('/auth/logout', { method: 'POST', body: JSON.stringify({ email, deviceFingerprint }) }),
  register: (payload) => request('/register', { method: 'POST', body: JSON.stringify(payload) }),
  getSettings: (email) => request(`/user/get-settings?email=${encodeURIComponent(email)}`),
  updateSettings: (payload) => request('/user/update-settings', { method: 'POST', body: JSON.stringify(payload) }),
  updateExclusionDates: (email, exclusionDates) =>
    request('/user/update-exclusion-dates', { method: 'POST', body: JSON.stringify({ email, exclusionDates }) }),
  toggleAutoReservation: (email, enabled) =>
    request('/user/toggle-auto-reservation', { method: 'POST', body: JSON.stringify({ email, enabled }) }),
  deleteAccount: (email) => request('/user/delete-account', { method: 'POST', body: JSON.stringify({ email }) }),
  checkReservation: (email, daysAhead = 5) =>
    request('/check-reservation', { method: 'POST', body: JSON.stringify({ email, daysAhead }) }),
  listReservations: (email) => request('/reservations', { method: 'POST', body: JSON.stringify({ email }) }),
  makeImmediateReservation: (email) =>
    request('/reservation/make-immediate', { method: 'POST', body: JSON.stringify({ email }) }),
  cancelReservation: (email) => request('/reservation/cancel', { method: 'POST', body: JSON.stringify({ email }) }),
  getStats: () => request('/stats'),
  pushSubscribe: (email, deviceFingerprint, subscription, platform) =>
    request('/user/push-subscribe', {
      method: 'POST',
      body: JSON.stringify({ email, deviceFingerprint, subscription, platform }),
    }),
}
