import React, { useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer
} from 'recharts'
import {
  Database, Briefcase, TrendingUp, Zap, Activity, Clock, Globe,
} from 'lucide-react'
import { format } from 'date-fns'
import { ptBR } from 'date-fns/locale'
import { useAppStore } from '../stores/appStore'
import { useDashboardStats } from '../hooks/useApi'
import StatCard from '../components/ui/StatCard'
import StatusBadge from '../components/ui/StatusBadge'
import ProgressBar from '../components/ui/ProgressBar'
import GlowCard from '../components/ui/GlowCard'
import { PageLoader } from '../components/ui/LoadingSpinner'

// Tooltip customizado para Recharts
function CustomTooltip({ active, payload, label }: { active?: boolean; payload?: { value: number }[]; label?: string }) {
  if (active && payload && payload.length) {
    return (
      <div className="tooltip-neon">
        <p className="text-text-muted text-xs mb-1">{label}</p>
        <p className="text-neon-cyan font-mono font-bold">{payload[0].value.toLocaleString('pt-BR')} items</p>
      </div>
    )
  }
  return null
}

function DomainTooltip({ active, payload }: { active?: boolean; payload?: { value: number; name?: string }[] }) {
  if (active && payload && payload.length) {
    return (
      <div className="tooltip-neon">
        <p className="text-neon-purple font-mono font-bold">{payload[0].value.toLocaleString('pt-BR')}</p>
      </div>
    )
  }
  return null
}

// Mock data para desenvolvimento
const mockHourlyData = Array.from({ length: 24 }, (_, i) => ({
  hour: `${String(i).padStart(2, '0')}:00`,
  count: Math.floor(Math.random() * 2000 + 200),
}))

const mockDomains = [
  { domain: 'reddit.com', count: 4521 },
  { domain: 'hackernews.com', count: 3892 },
  { domain: 'medium.com', count: 2876 },
  { domain: 'github.com', count: 2341 },
  { domain: 'techcrunch.com', count: 1987 },
  { domain: 'wired.com', count: 1654 },
  { domain: 'arstechnica.com', count: 1432 },
  { domain: 'theverge.com', count: 1123 },
  { domain: 'engadget.com', count: 987 },
  { domain: 'cnet.com', count: 765 },
]

const mockJobs = [
  { id: 'j001abc', url: 'https://reddit.com/r/programming', spider_type: 'news', status: 'RUNNING', items_count: 847, duration_seconds: 234, progress: 67 },
  { id: 'j002def', url: 'https://hackernews.com', spider_type: 'article', status: 'DONE', items_count: 1205, duration_seconds: 89 },
  { id: 'j003ghi', url: 'https://medium.com/tech', spider_type: 'generic', status: 'RUNNING', items_count: 432, duration_seconds: 156, progress: 45 },
  { id: 'j004jkl', url: 'https://github.com/trending', spider_type: 'generic', status: 'FAILED', items_count: 12, duration_seconds: 45 },
  { id: 'j005mno', url: 'https://techcrunch.com', spider_type: 'news', status: 'DONE', items_count: 892, duration_seconds: 124 },
]

// Feed de itens em tempo real
function RealtimeFeed() {
  const { realtimeItems } = useAppStore()

  return (
    <GlowCard color="green" className="h-full min-h-[300px]">
      <div className="p-4 border-b border-border-dim flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="live-dot" />
          <h3 className="text-text-primary font-semibold text-sm">Atividade em Tempo Real</h3>
        </div>
        <span className="text-text-muted text-xs font-mono">{realtimeItems.length} items</span>
      </div>
      <div className="overflow-hidden h-[260px] relative">
        {/* Gradiente de fade no topo */}
        <div className="absolute top-0 left-0 right-0 h-8 bg-gradient-to-b from-bg-card to-transparent z-10 pointer-events-none" />

        <div className="p-3 space-y-1.5 overflow-y-auto h-full">
          <AnimatePresence initial={false}>
            {realtimeItems.slice(0, 20).map((item) => (
              <motion.div
                key={item.id}
                initial={{ opacity: 0, y: -8, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, height: 0, marginBottom: 0 }}
                transition={{ duration: 0.3, ease: 'easeOut' }}
                className="flex items-center gap-2 p-2 rounded-lg bg-bg-base border border-border-dim hover:border-neon-green-dim transition-all duration-150"
              >
                <div
                  className="w-1.5 h-1.5 rounded-full bg-neon-green flex-shrink-0"
                  style={{ boxShadow: '0 0 4px rgba(0,255,136,0.8)' }}
                />
                <div className="min-w-0 flex-1">
                  <p className="text-text-primary text-xs truncate font-medium">
                    {item.title || 'Item sem título'}
                  </p>
                  <p className="text-text-muted text-xs font-mono truncate">{item.domain}</p>
                </div>
                <span className="text-neon-green text-xs font-mono flex-shrink-0 opacity-60">
                  {format(new Date(item.scraped_at), 'HH:mm:ss')}
                </span>
              </motion.div>
            ))}
          </AnimatePresence>

          {realtimeItems.length === 0 && (
            <div className="flex flex-col items-center justify-center h-48 gap-3">
              <Activity size={24} className="text-text-muted animate-pulse" />
              <p className="text-text-muted text-xs font-mono">Aguardando dados...</p>
            </div>
          )}
        </div>
      </div>
    </GlowCard>
  )
}

export default function Dashboard() {
  const { realtimeItems } = useAppStore()
  const { data: stats, isLoading } = useDashboardStats()

  // Sparkline data mock
  const sparkData = Array.from({ length: 12 }, (_, i) => ({
    value: Math.floor(Math.random() * 1000 + 200),
  }))

  const displayStats = stats || {
    total_items: 142_847,
    jobs_today: 47,
    success_rate: 94.2,
    items_per_hour: 3_240,
    active_jobs: 3,
    items_last_24h: mockHourlyData,
    top_domains: mockDomains,
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header indicador live */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="live-dot" />
          <span className="text-neon-green text-sm font-medium glow-text-green">🟢 Sistema Ativo</span>
        </div>
        <span className="text-text-muted text-xs font-mono">
          Atualizado: {format(new Date(), 'HH:mm:ss', { locale: ptBR })}
        </span>
      </div>

      {/* Linha 1: KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <StatCard
          title="Total de Items"
          value={displayStats.total_items}
          color="cyan"
          icon={<Database size={16} />}
          sparkline={sparkData}
          change={8.4}
          changeLabel="vs ontem"
          loading={isLoading}
        />
        <StatCard
          title="Jobs Hoje"
          value={displayStats.jobs_today}
          color="purple"
          icon={<Briefcase size={16} />}
          sparkline={sparkData}
          change={12.1}
          changeLabel="vs ontem"
          loading={isLoading}
        />
        <StatCard
          title="Taxa de Sucesso"
          value={displayStats.success_rate}
          color="green"
          icon={<TrendingUp size={16} />}
          suffix="%"
          decimals={1}
          sparkline={sparkData}
          change={-1.2}
          changeLabel="vs semana"
          loading={isLoading}
        />
        <StatCard
          title="Items / Hora"
          value={displayStats.items_per_hour}
          color="amber"
          icon={<Zap size={16} />}
          sparkline={sparkData}
          change={23.5}
          changeLabel="vs média"
          loading={isLoading}
        />
      </div>

      {/* Linha 2: Gráfico de área + Jobs recentes */}
      <div className="grid grid-cols-1 xl:grid-cols-5 gap-4">
        {/* Gráfico de área - 24h */}
        <GlowCard color="cyan" className="xl:col-span-3">
          <div className="p-4 border-b border-border-dim">
            <h3 className="text-text-primary font-semibold text-sm">Items Coletados — Últimas 24h</h3>
            <p className="text-text-muted text-xs font-mono mt-0.5">Distribuição horária</p>
          </div>
          <div className="p-4">
            {isLoading ? (
              <div className="h-48 bg-bg-surface rounded animate-pulse" />
            ) : (
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={displayStats.items_last_24h}>
                  <defs>
                    <linearGradient id="cyanGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#00d4ff" stopOpacity="0.3" />
                      <stop offset="100%" stopColor="#00d4ff" stopOpacity="0" />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                  <XAxis
                    dataKey="hour"
                    tick={{ fill: '#475569', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                    tickLine={false}
                    axisLine={false}
                    interval={3}
                  />
                  <YAxis
                    tick={{ fill: '#475569', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v) => v >= 1000 ? `${(v/1000).toFixed(1)}k` : v}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <Area
                    type="monotone"
                    dataKey="count"
                    stroke="#00d4ff"
                    strokeWidth={2}
                    fill="url(#cyanGradient)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </GlowCard>

        {/* Jobs Recentes */}
        <GlowCard color="purple" className="xl:col-span-2">
          <div className="p-4 border-b border-border-dim">
            <h3 className="text-text-primary font-semibold text-sm">Jobs Recentes</h3>
          </div>
          <div className="divide-y divide-border-dim">
            {mockJobs.map((job) => (
              <div key={job.id} className={`p-3 ${job.status === 'RUNNING' ? 'row-running' : ''}`}>
                <div className="flex items-start justify-between gap-2 mb-1.5">
                  <div className="min-w-0">
                    <p className="text-text-primary text-xs truncate">{job.url.replace('https://', '')}</p>
                    <p className="text-text-muted text-xs font-mono">{job.id}</p>
                  </div>
                  <StatusBadge status={job.status} size="sm" />
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-text-secondary font-mono">{job.items_count.toLocaleString('pt-BR')} items</span>
                  <span className="text-text-muted font-mono flex items-center gap-1">
                    <Clock size={10} />
                    {job.duration_seconds}s
                  </span>
                </div>
                {job.status === 'RUNNING' && job.progress !== undefined && (
                  <ProgressBar value={job.progress} size="xs" className="mt-1.5" color="cyan" />
                )}
              </div>
            ))}
          </div>
        </GlowCard>
      </div>

      {/* Linha 3: Top Domínios + Feed Tempo Real */}
      <div className="grid grid-cols-1 xl:grid-cols-5 gap-4">
        {/* Top 10 Domínios */}
        <GlowCard color="amber" className="xl:col-span-3">
          <div className="p-4 border-b border-border-dim">
            <h3 className="text-text-primary font-semibold text-sm">Top 10 Domínios Scrapeados</h3>
            <p className="text-text-muted text-xs font-mono mt-0.5">Por volume de itens coletados</p>
          </div>
          <div className="p-4">
            {isLoading ? (
              <div className="h-52 bg-bg-surface rounded animate-pulse" />
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart
                  data={displayStats.top_domains.slice(0, 10)}
                  layout="vertical"
                  margin={{ left: 0, right: 20, top: 0, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" horizontal={false} />
                  <XAxis
                    type="number"
                    tick={{ fill: '#475569', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v) => v >= 1000 ? `${(v/1000).toFixed(1)}k` : v}
                  />
                  <YAxis
                    type="category"
                    dataKey="domain"
                    tick={{ fill: '#94a3b8', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                    tickLine={false}
                    axisLine={false}
                    width={100}
                  />
                  <Tooltip content={<DomainTooltip />} />
                  <Bar
                    dataKey="count"
                    fill="url(#barGradient)"
                    radius={[0, 4, 4, 0]}
                  />
                  <defs>
                    <linearGradient id="barGradient" x1="0" y1="0" x2="1" y2="0">
                      <stop offset="0%" stopColor="rgba(124,58,237,0.6)" />
                      <stop offset="100%" stopColor="rgba(124,58,237,0.9)" />
                    </linearGradient>
                  </defs>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </GlowCard>

        {/* Feed em Tempo Real */}
        <div className="xl:col-span-2">
          <RealtimeFeed />
        </div>
      </div>
    </div>
  )
}
