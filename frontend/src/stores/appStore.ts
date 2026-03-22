import { create } from 'zustand'
import { devtools } from 'zustand/middleware'

export type JobStatus = 'PENDING' | 'RUNNING' | 'DONE' | 'FAILED' | 'CANCELLED'

export interface OperatorAction {
  required?: boolean
  type?: string
  message?: string
  open_url?: string
  next_step_command?: string
}

export interface JobMetadata {
  operator_action?: OperatorAction
  challenge_detected?: boolean
  challenge_source?: string
  challenge_detected_at?: string
  [key: string]: unknown
}

export interface Job {
  id: string
  url: string
  spider_type: string
  status: JobStatus
  items_count: number
  created_at: string
  started_at?: string
  finished_at?: string
  duration_seconds?: number
  error_message?: string
  render_js: boolean
  crawl_depth: number
  progress?: number
  metadata?: JobMetadata
}

export interface ScrapedItem {
  id: string
  job_id: string
  url: string
  title?: string
  content?: string
  domain: string
  spider_type: string
  scraped_at: string
  metadata?: Record<string, unknown>
}

export interface SystemStatus {
  api: 'online' | 'offline' | 'degraded'
  db: 'online' | 'offline' | 'degraded'
  redis: 'online' | 'offline' | 'degraded'
}

interface AppState {
  // Jobs
  jobs: Job[]
  activeJobsCount: number
  totalJobsToday: number
  itemsPerHour: number

  // Sistema
  systemStatus: SystemStatus
  isApiOnline: boolean

  // Items em tempo real
  realtimeItems: ScrapedItem[]
  totalItems: number
  successRate: number

  // UI
  currentPage: string

  // Actions
  setJobs: (jobs: Job[]) => void
  addJob: (job: Job) => void
  updateJob: (id: string, update: Partial<Job>) => void
  setActiveJobsCount: (count: number) => void
  setTotalJobsToday: (count: number) => void
  setItemsPerHour: (rate: number) => void
  setSystemStatus: (status: Partial<SystemStatus>) => void
  setApiOnline: (online: boolean) => void
  addRealtimeItem: (item: ScrapedItem) => void
  clearRealtimeItems: () => void
  setTotalItems: (count: number) => void
  setSuccessRate: (rate: number) => void
  setCurrentPage: (page: string) => void
}

export const useAppStore = create<AppState>()(
  devtools(
    (set) => ({
      // Estado inicial
      jobs: [],
      activeJobsCount: 0,
      totalJobsToday: 0,
      itemsPerHour: 0,

      systemStatus: {
        api: 'online',
        db: 'online',
        redis: 'online',
      },
      isApiOnline: true,

      realtimeItems: [],
      totalItems: 0,
      successRate: 0,

      currentPage: 'Dashboard',

      // Actions
      setJobs: (jobs) => set({ jobs }),

      addJob: (job) =>
        set((state) => ({
          jobs: [job, ...state.jobs],
          activeJobsCount: job.status === 'RUNNING' ? state.activeJobsCount + 1 : state.activeJobsCount,
        })),

      updateJob: (id, update) =>
        set((state) => {
          const oldJob = state.jobs.find((j) => j.id === id)
          const newJobs = state.jobs.map((j) => (j.id === id ? { ...j, ...update } : j))

          let deltaActive = 0
          if (oldJob) {
            const wasRunning = oldJob.status === 'RUNNING'
            const isNowRunning = (update.status ?? oldJob.status) === 'RUNNING'
            if (!wasRunning && isNowRunning) deltaActive = 1
            if (wasRunning && !isNowRunning) deltaActive = -1
          }

          return {
            jobs: newJobs,
            activeJobsCount: Math.max(0, state.activeJobsCount + deltaActive),
          }
        }),

      setActiveJobsCount: (count) => set({ activeJobsCount: count }),
      setTotalJobsToday: (count) => set({ totalJobsToday: count }),
      setItemsPerHour: (rate) => set({ itemsPerHour: rate }),

      setSystemStatus: (status) =>
        set((state) => ({
          systemStatus: { ...state.systemStatus, ...status },
        })),

      setApiOnline: (online) => set({ isApiOnline: online }),

      addRealtimeItem: (item) =>
        set((state) => ({
          realtimeItems: [item, ...state.realtimeItems].slice(0, 50),
        })),

      clearRealtimeItems: () => set({ realtimeItems: [] }),
      setTotalItems: (count) => set({ totalItems: count }),
      setSuccessRate: (rate) => set({ successRate: rate }),
      setCurrentPage: (page) => set({ currentPage: page }),
    }),
    { name: 'webscraper-store' }
  )
)
