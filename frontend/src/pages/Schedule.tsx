import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Calendar, Plus, Power, Trash2, Edit2, Clock,
  CheckCircle2, XCircle, X, ChevronDown,
} from 'lucide-react'
import { format, formatDistanceToNow, addMinutes } from 'date-fns'
import { ptBR } from 'date-fns/locale'
import clsx from 'clsx'
import { useSchedule, useCreateSchedule, useUpdateSchedule, useDeleteSchedule } from '../hooks/useApi'
import type { ScheduleEntry } from '../hooks/useApi'
import GlowCard from '../components/ui/GlowCard'
import NeonButton from '../components/ui/NeonButton'
import { PageLoader } from '../components/ui/LoadingSpinner'

// Parser cron para legível
function parseCron(cron: string): string {
  const presets: Record<string, string> = {
    '* * * * *': 'Todo minuto',
    '*/5 * * * *': 'A cada 5 minutos',
    '*/15 * * * *': 'A cada 15 minutos',
    '*/30 * * * *': 'A cada 30 minutos',
    '0 * * * *': 'A cada hora',
    '0 */2 * * *': 'A cada 2 horas',
    '0 */6 * * *': 'A cada 6 horas',
    '0 */12 * * *': 'A cada 12 horas',
    '0 0 * * *': 'Diariamente à meia-noite',
    '0 9 * * *': 'Diariamente às 9h',
    '0 9 * * 1': 'Segundas às 9h',
    '0 0 * * 0': 'Toda semana (Domingo)',
    '0 0 1 * *': 'Todo mês (dia 1)',
  }
  return presets[cron] || cron
}

// CRON Builder Visual
interface CronBuilderProps {
  value: string
  onChange: (v: string) => void
}

function CronBuilder({ value, onChange }: CronBuilderProps) {
  const [open, setOpen] = useState(false)

  const presets = [
    { label: 'A cada 5 minutos', value: '*/5 * * * *' },
    { label: 'A cada 15 minutos', value: '*/15 * * * *' },
    { label: 'A cada 30 minutos', value: '*/30 * * * *' },
    { label: 'A cada hora', value: '0 * * * *' },
    { label: 'A cada 2 horas', value: '0 */2 * * *' },
    { label: 'A cada 6 horas', value: '0 */6 * * *' },
    { label: 'A cada 12 horas', value: '0 */12 * * *' },
    { label: 'Diariamente (meia-noite)', value: '0 0 * * *' },
    { label: 'Diariamente às 9h', value: '0 9 * * *' },
    { label: 'Toda semana', value: '0 0 * * 0' },
    { label: 'Todo mês', value: '0 0 1 * *' },
  ]

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="input-neon w-full px-3 py-2 text-sm flex items-center justify-between text-left"
      >
        <span className="font-mono text-neon-cyan">{value || '* * * * *'}</span>
        <ChevronDown size={14} className={clsx('text-text-muted transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="absolute top-full left-0 right-0 mt-1 z-50 bg-bg-card border border-neon-cyan-dim rounded-lg shadow-glow-cyan overflow-hidden">
          {presets.map((p) => (
            <button
              key={p.value}
              type="button"
              onClick={() => { onChange(p.value); setOpen(false) }}
              className={clsx(
                'w-full px-3 py-2 text-left text-xs hover:bg-neon-cyan-dim transition-colors flex items-center justify-between',
                value === p.value ? 'bg-neon-cyan-dim text-neon-cyan' : 'text-text-secondary'
              )}
            >
              <span>{p.label}</span>
              <span className="font-mono text-text-muted text-xs">{p.value}</span>
            </button>
          ))}
          <div className="px-3 py-2 border-t border-border-dim">
            <label className="text-text-muted text-xs font-mono block mb-1">Personalizado:</label>
            <input
              type="text"
              value={value}
              onChange={(e) => onChange(e.target.value)}
              placeholder="min hora dia mês semana"
              className="input-neon w-full px-2 py-1 text-xs font-mono"
            />
          </div>
        </div>
      )}
    </div>
  )
}

// Mock data
const mockSchedules: ScheduleEntry[] = [
  {
    id: 'sc-001',
    name: 'Coleta Diária HackerNews',
    cron_expression: '0 9 * * *',
    spider_type: 'news',
    target_url: 'https://news.ycombinator.com',
    is_active: true,
    next_run: addMinutes(new Date(), 45).toISOString(),
    last_run: new Date(Date.now() - 86400000).toISOString(),
    run_history: Array.from({ length: 14 }, (_, i) => ({
      status: (Math.random() > 0.15 ? 'ok' : 'fail') as 'ok' | 'fail',
      timestamp: new Date(Date.now() - i * 86400000).toISOString(),
    })),
    created_at: new Date(Date.now() - 30 * 86400000).toISOString(),
  },
  {
    id: 'sc-002',
    name: 'Monitoramento Reddit',
    cron_expression: '*/30 * * * *',
    spider_type: 'generic',
    target_url: 'https://reddit.com/r/programming',
    is_active: true,
    next_run: addMinutes(new Date(), 12).toISOString(),
    last_run: new Date(Date.now() - 1800000).toISOString(),
    run_history: Array.from({ length: 20 }, (_, i) => ({
      status: (Math.random() > 0.05 ? 'ok' : 'fail') as 'ok' | 'fail',
      timestamp: new Date(Date.now() - i * 1800000).toISOString(),
    })),
    created_at: new Date(Date.now() - 15 * 86400000).toISOString(),
  },
  {
    id: 'sc-003',
    name: 'Preços E-commerce Semanal',
    cron_expression: '0 0 * * 0',
    spider_type: 'ecommerce',
    target_url: 'https://ecommerce.example.com/products',
    is_active: false,
    next_run: addMinutes(new Date(), 2880).toISOString(),
    last_run: new Date(Date.now() - 7 * 86400000).toISOString(),
    run_history: Array.from({ length: 8 }, (_, i) => ({
      status: (Math.random() > 0.2 ? 'ok' : 'fail') as 'ok' | 'fail',
      timestamp: new Date(Date.now() - i * 7 * 86400000).toISOString(),
    })),
    created_at: new Date(Date.now() - 60 * 86400000).toISOString(),
  },
]

// Historico dots (mini chart)
function RunHistoryDots({ history }: { history: Array<{ status: 'ok' | 'fail'; timestamp: string }> }) {
  const recent = history.slice(0, 14).reverse()
  return (
    <div className="flex items-center gap-1">
      {recent.map((run, i) => (
        <div
          key={i}
          title={`${run.status === 'ok' ? '✓' : '✗'} ${format(new Date(run.timestamp), 'dd/MM HH:mm', { locale: ptBR })}`}
          className={clsx(
            'w-2 h-2 rounded-sm',
            run.status === 'ok' ? 'bg-neon-green' : 'bg-neon-red'
          )}
          style={{
            opacity: 0.4 + (i / recent.length) * 0.6,
            boxShadow: run.status === 'ok' ? '0 0 3px rgba(0,255,136,0.5)' : '0 0 3px rgba(255,51,102,0.5)',
          }}
        />
      ))}
    </div>
  )
}

// Modal Novo Agendamento
function NewScheduleModal({ onClose, onCreate }: {
  onClose: () => void
  onCreate: (data: Omit<ScheduleEntry, 'id' | 'created_at' | 'run_history'>) => void
}) {
  const [name, setName] = useState('')
  const [cronExpr, setCronExpr] = useState('0 * * * *')
  const [url, setUrl] = useState('')
  const [spiderType, setSpiderType] = useState('generic')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onCreate({
      name,
      cron_expression: cronExpr,
      spider_type: spiderType,
      target_url: url,
      is_active: true,
      next_run: undefined,
      last_run: undefined,
    })
    onClose()
  }

  return (
    <div className="fixed inset-0 z-modal flex items-center justify-center modal-overlay" onClick={onClose}>
      <motion.div
        className="w-full max-w-lg mx-4"
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.9 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="glass-card border border-neon-cyan-mid rounded-xl overflow-hidden">
          <div className="p-4 border-b border-border-dim flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Calendar size={16} className="text-neon-cyan" />
              <h3 className="text-text-primary font-semibold">Novo Agendamento</h3>
            </div>
            <button onClick={onClose} className="text-text-muted hover:text-text-primary">
              <X size={16} />
            </button>
          </div>

          <form onSubmit={handleSubmit} className="p-5 space-y-4">
            <div>
              <label className="text-text-muted text-xs font-mono block mb-1.5">NOME</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Nome do agendamento..."
                required
                className="input-neon w-full px-3 py-2 text-sm"
              />
            </div>

            <div>
              <label className="text-text-muted text-xs font-mono block mb-1.5">URL ALVO</label>
              <input
                type="text"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://example.com"
                required
                className="input-neon w-full px-3 py-2 text-sm"
              />
            </div>

            <div>
              <label className="text-text-muted text-xs font-mono block mb-1.5">
                EXPRESSÃO CRON <span className="text-neon-cyan">{parseCron(cronExpr)}</span>
              </label>
              <CronBuilder value={cronExpr} onChange={setCronExpr} />
            </div>

            <div>
              <label className="text-text-muted text-xs font-mono block mb-1.5">SPIDER</label>
              <select
                value={spiderType}
                onChange={(e) => setSpiderType(e.target.value)}
                className="select-neon w-full px-3 py-2 text-sm"
              >
                <option value="generic">Genérico</option>
                <option value="news">Notícias</option>
                <option value="article">Artigo</option>
                <option value="ecommerce">E-commerce</option>
              </select>
            </div>

            <div className="flex gap-3 pt-2">
              <NeonButton variant="ghost" onClick={onClose} className="flex-1">Cancelar</NeonButton>
              <NeonButton type="submit" variant="primary" className="flex-1" icon={<Calendar size={14} />}>
                Criar Agendamento
              </NeonButton>
            </div>
          </form>
        </div>
      </motion.div>
    </div>
  )
}

// Card de Agendamento
function ScheduleCard({ schedule }: { schedule: ScheduleEntry }) {
  const { mutate: update } = useUpdateSchedule()
  const { mutate: del } = useDeleteSchedule()

  const nextRunDist = schedule.next_run
    ? formatDistanceToNow(new Date(schedule.next_run), { addSuffix: true, locale: ptBR })
    : 'Não agendado'

  const successRate = schedule.run_history.length > 0
    ? Math.round((schedule.run_history.filter(r => r.status === 'ok').length / schedule.run_history.length) * 100)
    : 0

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={clsx(
        'glass-card border p-5 transition-all duration-200',
        schedule.is_active
          ? 'border-neon-cyan-dim hover:border-neon-cyan-mid'
          : 'border-border-dim opacity-60'
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="min-w-0">
          <h3 className="text-text-primary font-semibold text-sm">{schedule.name}</h3>
          <p className="text-text-muted text-xs font-mono truncate">{schedule.target_url}</p>
        </div>
        <button
          onClick={() => update({ id: schedule.id, is_active: !schedule.is_active })}
          className={clsx(
            'flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-mono border transition-all flex-shrink-0',
            schedule.is_active
              ? 'text-neon-green bg-neon-green-dim border-neon-green-dim'
              : 'text-text-muted bg-bg-card border-border-dim'
          )}
        >
          <Power size={10} />
          {schedule.is_active ? 'Ativo' : 'Inativo'}
        </button>
      </div>

      {/* Cron */}
      <div className="bg-bg-surface rounded-lg px-3 py-2 mb-3 flex items-center justify-between">
        <code className="text-neon-cyan font-mono text-xs">{schedule.cron_expression}</code>
        <span className="text-text-secondary text-xs">{parseCron(schedule.cron_expression)}</span>
      </div>

      {/* Next run */}
      <div className="flex items-center gap-2 mb-3">
        <Clock size={12} className="text-neon-amber" />
        <span className="text-text-secondary text-xs">
          Próxima execução: <span className="text-neon-amber font-mono">{nextRunDist}</span>
        </span>
      </div>

      {/* Histórico */}
      <div className="mb-3">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-text-muted text-xs font-mono">HISTÓRICO</span>
          <span className={clsx(
            'text-xs font-mono',
            successRate >= 90 ? 'text-neon-green' : successRate >= 70 ? 'text-neon-amber' : 'text-neon-red'
          )}>
            {successRate}% sucesso
          </span>
        </div>
        <RunHistoryDots history={schedule.run_history} />
      </div>

      {/* Ações */}
      <div className="flex items-center gap-2 pt-3 border-t border-border-dim">
        <button
          onClick={() => del(schedule.id)}
          className="ml-auto p-1.5 rounded-lg border border-border-dim text-text-muted hover:border-neon-red-dim hover:text-neon-red transition-all"
          title="Deletar"
        >
          <Trash2 size={13} />
        </button>
      </div>
    </motion.div>
  )
}

export default function Schedule() {
  const { data, isLoading } = useSchedule()
  const [showNewModal, setShowNewModal] = useState(false)
  const { mutate: create } = useCreateSchedule()

  const displaySchedules = data || mockSchedules

  const activeCount = displaySchedules.filter(s => s.is_active).length

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <p className="text-text-muted text-sm">
          <span className="text-neon-cyan font-mono font-bold">{activeCount}</span> de{' '}
          <span className="text-neon-cyan font-mono font-bold">{displaySchedules.length}</span> agendamentos ativos
        </p>
        <NeonButton icon={<Plus size={14} />} onClick={() => setShowNewModal(true)}>
          Novo Agendamento
        </NeonButton>
      </div>

      {/* Timeline horizontal — resumo das próximas execuções */}
      <GlowCard color="cyan" className="p-4">
        <h3 className="text-text-secondary text-xs font-mono font-semibold mb-3 uppercase tracking-widest">
          TIMELINE DAS PRÓXIMAS EXECUÇÕES
        </h3>
        <div className="relative">
          {/* Linha base */}
          <div className="h-px bg-border-dim w-full" />
          {/* Markers */}
          <div className="flex items-start justify-between mt-2 gap-2">
            {displaySchedules.filter(s => s.is_active && s.next_run).map((s, i) => (
              <div key={s.id} className="flex flex-col items-center gap-1 min-w-0">
                <div
                  className="w-2 h-2 rounded-full -mt-3.5 mb-1"
                  style={{
                    background: ['#00d4ff', '#7c3aed', '#00ff88', '#ffb800'][i % 4],
                    boxShadow: `0 0 6px ${['rgba(0,212,255,0.6)', 'rgba(124,58,237,0.6)', 'rgba(0,255,136,0.6)', 'rgba(255,184,0,0.6)'][i % 4]}`,
                  }}
                />
                <span className="text-text-primary text-xs text-center truncate max-w-[80px]">{s.name}</span>
                <span className="text-text-muted text-xs font-mono">
                  {s.next_run ? format(new Date(s.next_run), 'HH:mm', { locale: ptBR }) : '—'}
                </span>
              </div>
            ))}
          </div>
        </div>
      </GlowCard>

      {/* Grid de Agendamentos */}
      {isLoading ? (
        <PageLoader label="Carregando agendamentos..." />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {displaySchedules.map((s) => (
            <ScheduleCard key={s.id} schedule={s} />
          ))}
        </div>
      )}

      {/* Modal */}
      <AnimatePresence>
        {showNewModal && (
          <NewScheduleModal
            onClose={() => setShowNewModal(false)}
            onCreate={(data) => create(data)}
          />
        )}
      </AnimatePresence>
    </div>
  )
}
