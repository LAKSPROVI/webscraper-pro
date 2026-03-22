import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Search, Filter, RefreshCw, Eye, XCircle, RotateCcw,
  Copy, Check, Globe, ChevronLeft, ChevronRight, AlertTriangle, ExternalLink,
} from 'lucide-react'
import { format } from 'date-fns'
import { ptBR } from 'date-fns/locale'
import clsx from 'clsx'
import { useJobs, useCancelJob, useRetryJob } from '../hooks/useApi'
import type { Job, JobStatus } from '../stores/appStore'
import StatusBadge from '../components/ui/StatusBadge'
import ProgressBar from '../components/ui/ProgressBar'
import NeonButton from '../components/ui/NeonButton'
import GlowCard from '../components/ui/GlowCard'
import { PageLoader } from '../components/ui/LoadingSpinner'
import toast from 'react-hot-toast'

type StatusFilter = 'ALL' | JobStatus

const statusFilters: { value: StatusFilter; label: string }[] = [
  { value: 'ALL', label: 'Todos' },
  { value: 'RUNNING', label: 'Executando' },
  { value: 'PENDING', label: 'Aguardando' },
  { value: 'DONE', label: 'Concluídos' },
  { value: 'FAILED', label: 'Falhos' },
]

const spiderColors: Record<string, string> = {
  generic: 'text-neon-cyan bg-neon-cyan-dim border-neon-cyan-dim',
  news: 'text-neon-purple bg-neon-purple-dim border-neon-purple-dim',
  article: 'text-neon-green bg-neon-green-dim border-neon-green-dim',
  ecommerce: 'text-neon-amber bg-neon-amber-dim border-neon-amber-dim',
}

function CopyableId({ id }: { id: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    navigator.clipboard.writeText(id)
    setCopied(true)
    toast.success('ID copiado!')
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1.5 group"
    >
      <span className="text-text-muted font-mono text-xs">{id.slice(0, 8)}...</span>
      <span className="opacity-0 group-hover:opacity-100 transition-opacity">
        {copied ? (
          <Check size={10} className="text-neon-green" />
        ) : (
          <Copy size={10} className="text-text-muted" />
        )}
      </span>
    </button>
  )
}

function OperatorActionAlert({ job }: { job: Job }) {
  const action = job.metadata?.operator_action
  if (!action?.required) {
    return null
  }

  const message = action.message || 'Intervenção do operador requerida para renovar sessão autenticada.'

  const handleOpenLogin = () => {
    if (!action.open_url) {
      toast.error('URL de login não disponível para este alerta')
      return
    }
    window.open(action.open_url, '_blank', 'noopener,noreferrer')
    toast.success('Página de login aberta em nova aba')
  }

  const handleCopyCommand = async () => {
    if (!action.next_step_command) {
      toast.error('Comando de ação não disponível')
      return
    }
    await navigator.clipboard.writeText(action.next_step_command)
    toast.success('Comando copiado para a área de transferência')
  }

  return (
    <GlowCard color="amber" className="p-4 border border-neon-amber-dim bg-neon-amber-dim/20">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 rounded-lg p-2 bg-neon-amber-dim border border-neon-amber-dim">
            <AlertTriangle size={16} className="text-neon-amber" />
          </div>
          <div>
            <p className="text-neon-amber text-sm font-semibold">Ação do operador necessária</p>
            <p className="text-text-secondary text-sm mt-1">{message}</p>
            <p className="text-text-muted text-xs font-mono mt-2">
              Job {job.id} • {job.url}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 sm:justify-end">
          <NeonButton
            variant="ghost"
            size="sm"
            onClick={handleOpenLogin}
            icon={<ExternalLink size={13} />}
          >
            Abrir login
          </NeonButton>
          <NeonButton
            variant="secondary"
            size="sm"
            onClick={handleCopyCommand}
            icon={<Copy size={13} />}
          >
            Copiar comando
          </NeonButton>
        </div>
      </div>
    </GlowCard>
  )
}

function JobRow({ job, onViewItems }: { job: Job; onViewItems: (job: Job) => void }) {
  const { mutate: cancel, isPending: cancelling } = useCancelJob()
  const { mutate: retry, isPending: retrying } = useRetryJob()

  const isRunning = job.status === 'RUNNING'
  const domain = (() => {
    try { return new URL(job.url).hostname } catch { return job.url }
  })()

  const duration = job.duration_seconds
    ? job.duration_seconds < 60
      ? `${job.duration_seconds}s`
      : `${Math.floor(job.duration_seconds / 60)}m ${job.duration_seconds % 60}s`
    : '—'

  return (
    <tr
      className={clsx(
        'border-b border-border-dim transition-all duration-150',
        'hover:bg-bg-card-hover group',
        isRunning && 'row-running bg-opacity-5 bg-neon-cyan'
      )}
    >
      {/* ID */}
      <td className="px-4 py-3">
        <CopyableId id={job.id} />
      </td>

      {/* URL */}
      <td className="px-4 py-3">
        <div className="flex items-center gap-2 min-w-0">
          <Globe size={12} className="text-text-muted flex-shrink-0" />
          <a
            href={job.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-text-primary text-xs truncate max-w-[200px] hover:text-neon-cyan transition-colors"
          >
            {domain}
          </a>
        </div>
      </td>

      {/* Spider */}
      <td className="px-4 py-3">
        <span className={clsx(
          'px-2 py-0.5 rounded-full text-xs font-mono font-medium border',
          spiderColors[job.spider_type] || 'text-text-secondary bg-bg-surface border-border-dim'
        )}>
          {job.spider_type}
        </span>
      </td>

      {/* Status */}
      <td className="px-4 py-3">
        <div className="flex flex-col gap-1">
          <StatusBadge status={job.status} size="sm" />
          {isRunning && job.progress !== undefined && (
            <ProgressBar value={job.progress} size="xs" color="cyan" className="w-20" />
          )}
        </div>
      </td>

      {/* Items */}
      <td className="px-4 py-3">
        <span className="text-text-primary font-mono text-xs">
          {job.items_count.toLocaleString('pt-BR')}
        </span>
      </td>

      {/* Duração */}
      <td className="px-4 py-3">
        <span className="text-text-muted font-mono text-xs">{duration}</span>
      </td>

      {/* Criado */}
      <td className="px-4 py-3">
        <span className="text-text-muted font-mono text-xs">
          {format(new Date(job.created_at), 'dd/MM HH:mm', { locale: ptBR })}
        </span>
      </td>

      {/* Ações */}
      <td className="px-4 py-3">
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={() => onViewItems(job)}
            className="p-1.5 rounded-lg hover:bg-neon-cyan-dim hover:text-neon-cyan text-text-muted transition-all duration-150"
            title="Ver items"
          >
            <Eye size={13} />
          </button>
          {(job.status === 'RUNNING' || job.status === 'PENDING') && (
            <button
              onClick={() => cancel(job.id)}
              disabled={cancelling}
              className="p-1.5 rounded-lg hover:bg-neon-red-dim hover:text-neon-red text-text-muted transition-all duration-150"
              title="Cancelar"
            >
              <XCircle size={13} />
            </button>
          )}
          {job.status === 'FAILED' && (
            <button
              onClick={() => retry(job.id)}
              disabled={retrying}
              className="p-1.5 rounded-lg hover:bg-neon-green-dim hover:text-neon-green text-text-muted transition-all duration-150"
              title="Re-executar"
            >
              <RotateCcw size={13} />
            </button>
          )}
        </div>
      </td>
    </tr>
  )
}

// Modal de items do job
function JobItemsModal({ job, onClose }: { job: Job; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-modal flex items-center justify-center modal-overlay" onClick={onClose}>
      <motion.div
        className="w-full max-w-2xl mx-4"
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.9 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="glass-card border border-neon-cyan-mid rounded-xl overflow-hidden">
          <div className="p-4 border-b border-border-dim flex items-center justify-between">
            <div>
              <h3 className="text-text-primary font-semibold">Items do Job</h3>
              <p className="text-text-muted text-xs font-mono">{job.id}</p>
            </div>
            <NeonButton variant="ghost" size="sm" onClick={onClose}>Fechar</NeonButton>
          </div>
          <div className="p-4">
            <div className="flex items-center justify-between mb-3">
              <div>
                <p className="text-text-secondary text-sm">{job.url}</p>
                <p className="text-neon-cyan font-mono text-lg font-bold">{job.items_count.toLocaleString('pt-BR')} items coletados</p>
              </div>
              <StatusBadge status={job.status} />
            </div>
            <div className="text-text-muted text-sm text-center py-8 font-mono">
              Visualização completa disponível com a API conectada
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  )
}

export default function Jobs() {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('ALL')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [selectedJob, setSelectedJob] = useState<Job | null>(null)

  const { data, isLoading, refetch } = useJobs({
    status: statusFilter === 'ALL' ? undefined : statusFilter,
    search: search || undefined,
    page,
    limit: 15,
  })

  // Mock data
  const mockJobs: Job[] = Array.from({ length: 15 }, (_, i) => ({
    id: `job-${(i + 1).toString().padStart(8, '0')}`,
    url: `https://${['reddit.com', 'hackernews.com', 'medium.com', 'github.com', 'techcrunch.com'][i % 5]}/post/${i * 100}`,
    spider_type: ['generic', 'news', 'article', 'ecommerce'][i % 4],
    status: (['RUNNING', 'DONE', 'DONE', 'FAILED', 'PENDING', 'DONE', 'RUNNING'][i % 7]) as JobStatus,
    items_count: Math.floor(Math.random() * 2000 + 50),
    created_at: new Date(Date.now() - i * 3600000).toISOString(),
    started_at: new Date(Date.now() - i * 3600000 + 60000).toISOString(),
    duration_seconds: Math.floor(Math.random() * 600 + 30),
    render_js: i % 3 === 0,
    crawl_depth: (i % 3) + 1,
    progress: (['RUNNING'].includes(['RUNNING', 'DONE', 'DONE', 'FAILED', 'PENDING', 'DONE', 'RUNNING'][i % 7]) ? Math.floor(Math.random() * 80 + 20) : undefined),
  }))

  const displayJobs = data?.items || mockJobs
  const totalPages = data?.pages || 3
  const total = data?.total || 47
  const operatorActionJob = displayJobs.find((job) => Boolean(job.metadata?.operator_action?.required))

  return (
    <div className="space-y-4 animate-fade-in">
      {operatorActionJob && <OperatorActionAlert job={operatorActionJob} />}

      {/* Filtros */}
      <GlowCard color="cyan" className="p-4">
        <div className="flex flex-col sm:flex-row gap-3">
          {/* Busca */}
          <div className="relative flex-1">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar por URL, ID ou spider..."
              className="input-neon w-full pl-9 pr-4 py-2 text-sm"
            />
          </div>

          {/* Status Filters */}
          <div className="flex flex-wrap gap-1.5">
            {statusFilters.map((f) => (
              <button
                key={f.value}
                onClick={() => { setStatusFilter(f.value); setPage(1) }}
                className={clsx(
                  'px-3 py-1.5 rounded-lg text-xs font-mono font-medium border transition-all duration-200',
                  statusFilter === f.value
                    ? 'bg-neon-cyan-dim border-neon-cyan-mid text-neon-cyan'
                    : 'bg-bg-card border-border-dim text-text-secondary hover:border-border-mid'
                )}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* Atualizar */}
          <NeonButton
            variant="ghost"
            size="sm"
            onClick={() => refetch()}
            icon={<RefreshCw size={13} />}
          >
            Atualizar
          </NeonButton>
        </div>
      </GlowCard>

      {/* Tabela */}
      <GlowCard color="cyan" className="overflow-hidden">
        {/* Header da tabela */}
        <div className="px-4 py-3 border-b border-border-dim flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-text-secondary text-sm">
              <span className="text-neon-cyan font-mono font-bold">{total}</span> jobs encontrados
            </span>
          </div>
        </div>

        {/* Tabela */}
        <div className="overflow-x-auto">
          {isLoading ? (
            <PageLoader label="Carregando jobs..." />
          ) : (
            <table className="min-w-full">
              <thead>
                <tr className="bg-bg-card border-b border-border-mid">
                  {['ID', 'URL', 'Spider', 'Status', 'Items', 'Duração', 'Criado', ''].map((h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left text-xs font-semibold text-text-muted uppercase tracking-widest font-mono whitespace-nowrap"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {displayJobs.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-4 py-16 text-center">
                      <div className="flex flex-col items-center gap-3">
                        <div className="text-3xl opacity-20">🕸️</div>
                        <p className="text-text-muted text-sm font-mono">Nenhum job encontrado</p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  displayJobs.map((job) => (
                    <JobRow
                      key={job.id}
                      job={job}
                      onViewItems={setSelectedJob}
                    />
                  ))
                )}
              </tbody>
            </table>
          )}
        </div>

        {/* Paginação */}
        {totalPages > 1 && (
          <div className="px-4 py-3 border-t border-border-dim flex items-center justify-between">
            <span className="text-text-muted text-xs font-mono">
              Página {page} de {totalPages}
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage(Math.max(1, page - 1))}
                disabled={page === 1}
                className="p-1.5 rounded-lg border border-border-dim text-text-muted hover:border-neon-cyan-mid hover:text-neon-cyan transition-all disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <ChevronLeft size={14} />
              </button>

              {[...Array(Math.min(5, totalPages))].map((_, i) => {
                const pageNum = i + 1
                return (
                  <button
                    key={pageNum}
                    onClick={() => setPage(pageNum)}
                    className={clsx(
                      'w-7 h-7 rounded-lg text-xs font-mono transition-all',
                      page === pageNum
                        ? 'bg-neon-cyan-dim text-neon-cyan border border-neon-cyan-mid'
                        : 'text-text-muted hover:text-text-primary border border-transparent hover:border-border-mid'
                    )}
                  >
                    {pageNum}
                  </button>
                )
              })}

              <button
                onClick={() => setPage(Math.min(totalPages, page + 1))}
                disabled={page === totalPages}
                className="p-1.5 rounded-lg border border-border-dim text-text-muted hover:border-neon-cyan-mid hover:text-neon-cyan transition-all disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </GlowCard>

      {/* Modal de items */}
      <AnimatePresence>
        {selectedJob && (
          <JobItemsModal job={selectedJob} onClose={() => setSelectedJob(null)} />
        )}
      </AnimatePresence>
    </div>
  )
}
