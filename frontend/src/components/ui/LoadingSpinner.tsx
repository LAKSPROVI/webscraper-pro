import clsx from 'clsx'

interface LoadingSpinnerProps {
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  color?: 'cyan' | 'purple' | 'green' | 'white'
  className?: string
  label?: string
}

const sizeMap = {
  xs: { outer: 'w-4 h-4', inner: 'w-2 h-2', border: 'border-2' },
  sm: { outer: 'w-6 h-6', inner: 'w-3 h-3', border: 'border-2' },
  md: { outer: 'w-8 h-8', inner: 'w-4 h-4', border: 'border-2' },
  lg: { outer: 'w-12 h-12', inner: 'w-6 h-6', border: 'border-[3px]' },
  xl: { outer: 'w-16 h-16', inner: 'w-8 h-8', border: 'border-4' },
}

const colorMap = {
  cyan: { track: 'border-neon-cyan-dim', active: 'border-t-neon-cyan', glow: '0 0 12px rgba(0,212,255,0.6)' },
  purple: { track: 'border-purple-800', active: 'border-t-purple-400', glow: '0 0 12px rgba(124,58,237,0.6)' },
  green: { track: 'border-neon-green-dim', active: 'border-t-neon-green', glow: '0 0 12px rgba(0,255,136,0.6)' },
  white: { track: 'border-white/20', active: 'border-t-white', glow: 'none' },
}

export default function LoadingSpinner({
  size = 'md',
  color = 'cyan',
  className,
  label,
}: LoadingSpinnerProps) {
  const sizeConf = sizeMap[size]
  const colorConf = colorMap[color]

  return (
    <div className={clsx('flex flex-col items-center gap-2', className)}>
      <div className="relative flex items-center justify-center" style={{ width: sizeMap[size].outer.split(' ')[0].replace('w-', '') + 'px' }}>
        <div
          className={clsx('rounded-full animate-spin', sizeConf.outer, sizeConf.border, colorConf.track, colorConf.active)}
          style={{
            filter: `drop-shadow(${colorConf.glow})`,
          }}
        />
        {/* Dot central */}
        <div
          className={clsx('absolute rounded-full', sizeConf.inner)}
          style={{
            background: `radial-gradient(circle, rgba(0,212,255,0.2) 0%, transparent 70%)`,
          }}
        />
      </div>
      {label && (
        <span className="text-text-secondary text-xs font-mono animate-pulse">{label}</span>
      )}
    </div>
  )
}

// Spinner full-page
export function PageLoader({ label = 'Carregando...' }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[300px] gap-4">
      {/* Spinner triplo */}
      <div className="relative w-16 h-16">
        <div
          className="absolute inset-0 rounded-full border-2 border-neon-cyan-dim border-t-neon-cyan animate-spin"
          style={{ animationDuration: '1s' }}
        />
        <div
          className="absolute inset-2 rounded-full border-2 border-neon-purple-dim border-t-purple-400 animate-spin"
          style={{ animationDuration: '1.5s', animationDirection: 'reverse' }}
        />
        <div
          className="absolute inset-4 rounded-full border-2 border-neon-green-dim border-t-neon-green animate-spin"
          style={{ animationDuration: '2s' }}
        />
      </div>
      <p className="text-text-secondary text-sm font-mono">{label}</p>
    </div>
  )
}
