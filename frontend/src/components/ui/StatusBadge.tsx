import clsx from 'clsx'
import type { JobStatus } from '../../stores/appStore'

interface StatusBadgeProps {
  status: JobStatus | string
  size?: 'sm' | 'md' | 'lg'
  showDot?: boolean
  className?: string
}

const statusConfig: Record<string, { label: string; className: string; dot?: boolean }> = {
  PENDING: {
    label: 'Aguardando',
    className: 'badge-pending',
    dot: true,
  },
  RUNNING: {
    label: 'Executando',
    className: 'badge-running',
    dot: true,
  },
  DONE: {
    label: 'Concluído',
    className: 'badge-done',
    dot: false,
  },
  FAILED: {
    label: 'Falhou',
    className: 'badge-failed',
    dot: false,
  },
  CANCELLED: {
    label: 'Cancelado',
    className: 'bg-bg-surface border border-border-mid text-text-muted',
    dot: false,
  },
}

const sizeMap = {
  sm: 'px-2 py-0.5 text-xs',
  md: 'px-2.5 py-1 text-xs',
  lg: 'px-3 py-1.5 text-sm',
}

export default function StatusBadge({ status, size = 'md', showDot = true, className }: StatusBadgeProps) {
  const config = statusConfig[status] || {
    label: status,
    className: 'bg-bg-surface border border-border-mid text-text-secondary',
    dot: false,
  }

  const isRunning = status === 'RUNNING'

  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full font-mono font-medium',
        sizeMap[size],
        config.className,
        className
      )}
    >
      {showDot && (
        <span
          className={clsx(
            'rounded-full flex-shrink-0',
            size === 'sm' ? 'w-1.5 h-1.5' : 'w-2 h-2',
            isRunning ? 'live-dot' : status === 'DONE' ? 'bg-neon-green' : status === 'FAILED' ? 'bg-neon-red' : status === 'CANCELLED' ? 'bg-text-muted' : 'bg-neon-amber'
          )}
        />
      )}
      {isRunning && (
        <span
          className="inline-block"
          style={{
            width: size === 'sm' ? '10px' : '12px',
            height: size === 'sm' ? '10px' : '12px',
            border: '2px solid rgba(0,212,255,0.3)',
            borderTop: '2px solid #00d4ff',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite',
            flexShrink: 0,
          }}
        />
      )}
      {config.label}
    </span>
  )
}
