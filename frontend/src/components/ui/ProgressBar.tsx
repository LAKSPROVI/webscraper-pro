import clsx from 'clsx'

interface ProgressBarProps {
  value: number // 0-100
  max?: number
  color?: 'cyan' | 'purple' | 'green' | 'amber' | 'red'
  size?: 'xs' | 'sm' | 'md' | 'lg'
  showLabel?: boolean
  animated?: boolean
  className?: string
  label?: string
}

const colorMap = {
  cyan: {
    bg: 'bg-neon-cyan-dim',
    fill: 'bg-neon-cyan',
    glow: 'shadow-glow-cyan',
    text: 'text-neon-cyan',
  },
  purple: {
    bg: 'bg-neon-purple-dim',
    fill: 'bg-neon-purple',
    glow: 'shadow-glow-purple',
    text: 'text-purple-300',
  },
  green: {
    bg: 'bg-neon-green-dim',
    fill: 'bg-neon-green',
    glow: 'shadow-glow-green',
    text: 'text-neon-green',
  },
  amber: {
    bg: 'bg-neon-amber-dim',
    fill: 'bg-neon-amber',
    glow: 'shadow-glow-amber',
    text: 'text-neon-amber',
  },
  red: {
    bg: 'bg-neon-red-dim',
    fill: 'bg-neon-red',
    glow: 'shadow-glow-red',
    text: 'text-neon-red',
  },
}

const heightMap = {
  xs: 'h-1',
  sm: 'h-1.5',
  md: 'h-2',
  lg: 'h-3',
}

export default function ProgressBar({
  value,
  max = 100,
  color = 'cyan',
  size = 'md',
  showLabel = false,
  animated = true,
  className,
  label,
}: ProgressBarProps) {
  const percentage = Math.min(100, Math.max(0, (value / max) * 100))
  const colorConf = colorMap[color]

  return (
    <div className={clsx('flex flex-col gap-1', className)}>
      {(showLabel || label) && (
        <div className="flex items-center justify-between">
          {label && <span className="text-xs text-text-secondary font-mono">{label}</span>}
          {showLabel && (
            <span className={clsx('text-xs font-mono font-medium', colorConf.text)}>
              {Math.round(percentage)}%
            </span>
          )}
        </div>
      )}
      <div
        className={clsx(
          'w-full rounded-full overflow-hidden',
          heightMap[size],
          colorConf.bg
        )}
      >
        <div
          className={clsx(
            'h-full rounded-full transition-all duration-500 ease-out',
            colorConf.fill,
            animated && 'shimmer-bar',
          )}
          style={{
            width: `${percentage}%`,
            boxShadow: percentage > 5 ? `0 0 8px currentColor` : 'none',
          }}
        />
      </div>
    </div>
  )
}
