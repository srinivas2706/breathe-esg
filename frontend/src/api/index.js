import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL || '/api/v1'

const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

// Attach JWT token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Auto-refresh on 401
api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config
    if (err.response?.status === 401 && !original._retry) {
      original._retry = true
      const refresh = localStorage.getItem('refresh_token')
      if (refresh) {
        try {
          const { data } = await axios.post(`${BASE_URL}/auth/token/refresh/`, { refresh })
          localStorage.setItem('access_token', data.access)
          original.headers.Authorization = `Bearer ${data.access}`
          return api(original)
        } catch {
          localStorage.clear()
          window.location.href = '/login'
        }
      }
    }
    return Promise.reject(err)
  }
)

// ── Auth ──────────────────────────────────────────────────────────────────
export const authAPI = {
  login: (username, password) =>
    api.post('/auth/token/', { username, password }),
  me: () => api.get('/users/me/'),
}

// ── Ingestion ─────────────────────────────────────────────────────────────
export const ingestionAPI = {
  getBatches: (params) => api.get('/ingestion/batches/', { params }),
  getBatch: (id) => api.get(`/ingestion/batches/${id}/`),
  getRawRecords: (id, params) => api.get(`/ingestion/batches/${id}/raw_records/`, { params }),
  upload: (formData) =>
    api.post('/ingestion/batches/upload/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
}

// ── Emissions ─────────────────────────────────────────────────────────────
export const emissionsAPI = {
  getRecords: (params) => api.get('/emissions/', { params }),
  getRecord: (id) => api.get(`/emissions/${id}/`),
  review: (id, data) => api.patch(`/emissions/${id}/review/`, data),
  bulkApprove: (ids, note) => api.post('/emissions/bulk_approve/', { ids, note }),
  getSummary: (params) => api.get('/emissions/summary/', { params }),
}

// ── Audit ─────────────────────────────────────────────────────────────────
export const auditAPI = {
  getLogs: (params) => api.get('/audit/', { params }),
}

export default api
