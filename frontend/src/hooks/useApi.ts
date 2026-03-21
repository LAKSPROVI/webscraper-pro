import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import toast from 'react-hot-toast'
import type { Job, ScrapedItem } from '../stores/appStore'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
})

// Interceptor para erros globais
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const message = error.response?.data?.detail || error.message || 'Erro desconhecido'
    if (error.response?.status !== 404) {
      toast.error(`API: ${message}`)
    }
    return Promise.reject(error)
  }
)

// ============================================================
// TIPOS
// ============================================================

export interface JobsListParams {
  status?: string
  search?: string
  page?: number
  limit?: number
  date_from?: string
  date_to?: string
}

export interface ScrapeRequest {
  url: string
  spider_type: string
  render_js?: boolean
  crawl_depth?: number
  config?: Record<string, unknown>
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  limit: number
  pages: number
}

export interface DataSearchParams {
  q?: string
  domain?: string
  spider_type?: string
  date_from?: string
  date_to?: string
  page?: number
  limit?: number
}

export interface SpiderConfig {
  id: string
  name: string
  type: string
  description?: string
  is_active: boolean
  config_yaml: string
  last_used?: string
  total_runs: number
  created_at: string
}

export interface ScheduleEntry {
  id: string
  name: string
  cron_expression: string
  spider_type: string
  target_url: string
  is_active: boolean
  next_run?: string
  last_run?: string
  run_history: Array<{ status: 'ok' | 'fail'; timestamp: string }>
  created_at: string
}

export interface DashboardStats {
  total_items: number
  jobs_today: number
  success_rate: number
  items_per_hour: number
  active_jobs: number
  items_last_24h: Array<{ hour: string; count: number }>
  top_domains: Array<{ domain: string; count: number }>
}

export interface HealthStatus {
  api: 'online' | 'offline' | 'degraded'
  db: 'online' | 'offline' | 'degraded'
  redis: 'online' | 'offline' | 'degraded'
  version: string
}

// ============================================================
// HEALTH / STATUS
// ============================================================

export function useHealthCheck() {
  return useQuery<HealthStatus>({
    queryKey: ['health'],
    queryFn: async () => {
      const { data } = await api.get<HealthStatus>('/api/v1/health')
      return data
    },
    refetchInterval: 30000,
    retry: false,
  })
}

// ============================================================
// DASHBOARD STATS
// ============================================================

export function useDashboardStats() {
  return useQuery<DashboardStats>({
    queryKey: ['dashboard-stats'],
    queryFn: async () => {
      const { data } = await api.get<DashboardStats>('/api/v1/stats/dashboard')
      return data
    },
    refetchInterval: 10000,
  })
}

// ============================================================
// JOBS
// ============================================================

export function useJobs(params: JobsListParams = {}) {
  return useQuery<PaginatedResponse<Job>>({
    queryKey: ['jobs', params],
    queryFn: async () => {
      const { data } = await api.get<PaginatedResponse<Job>>('/api/v1/jobs', { params })
      return data
    },
    refetchInterval: 5000,
  })
}

export function useJob(id: string) {
  return useQuery<Job>({
    queryKey: ['job', id],
    queryFn: async () => {
      const { data } = await api.get<Job>(`/api/v1/jobs/${id}`)
      return data
    },
    enabled: !!id,
  })
}

export function useJobItems(jobId: string, page = 1, limit = 20) {
  return useQuery<PaginatedResponse<ScrapedItem>>({
    queryKey: ['job-items', jobId, page, limit],
    queryFn: async () => {
      const { data } = await api.get<PaginatedResponse<ScrapedItem>>(`/api/v1/jobs/${jobId}/items`, {
        params: { page, limit },
      })
      return data
    },
    enabled: !!jobId,
  })
}

export function useScrape() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (request: ScrapeRequest) => {
      const { data } = await api.post<Job>('/api/v1/scrape', request)
      return data
    },
    onSuccess: (data) => {
      toast.success(`Job iniciado: ${data.id.slice(0, 8)}...`)
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] })
    },
    onError: () => {
      toast.error('Falha ao iniciar scraping')
    },
  })
}

export function useCancelJob() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (jobId: string) => {
      await api.post(`/api/v1/jobs/${jobId}/cancel`)
      return jobId
    },
    onSuccess: () => {
      toast.success('Job cancelado')
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })
}

export function useRetryJob() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (jobId: string) => {
      const { data } = await api.post<Job>(`/api/v1/jobs/${jobId}/retry`)
      return data
    },
    onSuccess: () => {
      toast.success('Job re-executado')
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })
}

// ============================================================
// DATA EXPLORER
// ============================================================

export function useData(params: DataSearchParams = {}) {
  return useQuery<PaginatedResponse<ScrapedItem>>({
    queryKey: ['data', params],
    queryFn: async () => {
      const { data } = await api.get<PaginatedResponse<ScrapedItem>>('/api/v1/data', { params })
      return data
    },
    enabled: true,
  })
}

export function useDataItem(id: string) {
  return useQuery<ScrapedItem>({
    queryKey: ['data-item', id],
    queryFn: async () => {
      const { data } = await api.get<ScrapedItem>(`/api/v1/data/${id}`)
      return data
    },
    enabled: !!id,
  })
}

// ============================================================
// SPIDERS
// ============================================================

export function useSpiders() {
  return useQuery<SpiderConfig[]>({
    queryKey: ['spiders'],
    queryFn: async () => {
      const { data } = await api.get<SpiderConfig[]>('/api/v1/spiders')
      return data
    },
  })
}

export function useCreateSpider() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (config: Omit<SpiderConfig, 'id' | 'created_at' | 'total_runs'>) => {
      const { data } = await api.post<SpiderConfig>('/api/v1/spiders', config)
      return data
    },
    onSuccess: () => {
      toast.success('Spider criado com sucesso')
      queryClient.invalidateQueries({ queryKey: ['spiders'] })
    },
  })
}

export function useUpdateSpider() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ id, ...config }: Partial<SpiderConfig> & { id: string }) => {
      const { data } = await api.put<SpiderConfig>(`/api/v1/spiders/${id}`, config)
      return data
    },
    onSuccess: () => {
      toast.success('Spider atualizado')
      queryClient.invalidateQueries({ queryKey: ['spiders'] })
    },
  })
}

export function useDeleteSpider() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/v1/spiders/${id}`)
      return id
    },
    onSuccess: () => {
      toast.success('Spider removido')
      queryClient.invalidateQueries({ queryKey: ['spiders'] })
    },
  })
}

// ============================================================
// SCHEDULE
// ============================================================

export function useSchedule() {
  return useQuery<ScheduleEntry[]>({
    queryKey: ['schedule'],
    queryFn: async () => {
      const { data } = await api.get<ScheduleEntry[]>('/api/v1/schedule')
      return data
    },
    refetchInterval: 60000,
  })
}

export function useCreateSchedule() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (entry: Omit<ScheduleEntry, 'id' | 'created_at' | 'run_history'>) => {
      const { data } = await api.post<ScheduleEntry>('/api/v1/schedule', entry)
      return data
    },
    onSuccess: () => {
      toast.success('Agendamento criado')
      queryClient.invalidateQueries({ queryKey: ['schedule'] })
    },
  })
}

export function useUpdateSchedule() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ id, ...entry }: Partial<ScheduleEntry> & { id: string }) => {
      const { data } = await api.put<ScheduleEntry>(`/api/v1/schedule/${id}`, entry)
      return data
    },
    onSuccess: () => {
      toast.success('Agendamento atualizado')
      queryClient.invalidateQueries({ queryKey: ['schedule'] })
    },
  })
}

export function useDeleteSchedule() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/v1/schedule/${id}`)
      return id
    },
    onSuccess: () => {
      toast.success('Agendamento removido')
      queryClient.invalidateQueries({ queryKey: ['schedule'] })
    },
  })
}

export { api }
