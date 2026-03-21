import React, { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import clsx from 'clsx'

type StatColor = 'cyan' | 'purple' | 'green' | 'amber'

interface SparklineData {
  value: number
}

interface StatCardProps {
  title: string
  value: number
  unit?: string
  color?: StatColor
  icon?: React.ReactNode
  change?: number // percentual de mudança
  changeLabel?: string
  sparkline?: SparklineData[]
  prefix?: string
  suffix?: string
  loading?: boolean
  className?: string
  decimals?: number
}

const colorConfig: Record<StatColor, {
  text: string
  border: string
  iconBg: string
  spark: string
  gradient: string
}> = {
  cyan: {
    text: 'text-neon-cyan',
    border: 'border-neon-cyan-dim hover:border-neon-cyan-mid',
    iconBg: 'bg-neon-cyan-dim',
    spark: '#00d4ff',
    gradient: 'from-neon-cyan-dim',
  },
  purple: {
    text: 'text-purple-300',
    border: 'border-neon-purple-dim hover:border-neon-purple-mid',
    iconBg: 'bg-neon-purple-dim',
    spark: '#a78bfa',
    gradient: 'from-neon-purple-dim',
  },
  green: {
    text: 'text-neon-green',
    border: 'border-neon-green-dim hover:border-neon-green-mid',
    iconBg: 'bg-neon-green-dim',
    spark: '#00ff88',
    gradient: 'from-neon-green-dim',
  },
  amber: {
    text: 'text-neon-amber',
    border: 'border-neon-amber-dim',
    iconBg: 'bg-neon-amber-dim',
    spark: '#ffb800',
    gradient: 'from-neon-amber-dim',
  },
}

// Hook count-up
function useCountUp(target: number, duration = 1200, decimals = 0) {
  const [current, setCurrent] = useState(0)
  const frameRef = useRef<number | null>(null)
  const startRef = useRef<number | null>(null)
  const prevTargetRef = useRef(0)

  useEffect(() => {
    const startValue = prevTargetRef.current
    prevTargetRef.current = target

    if (frameRef.current) cancelAnimationFrame(frameRef.current)

    const animate = (timestamp: number) => {
      if (!startRef.current) startRef.current = timestamp
      const elapsed = timestamp - startRef.current
      const progress = Math.min(elapsed / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3) // ease-out cubic

      const value = startValue + (target - startValue) * eased
      setCurrent(parseFloat(value.toFixed(decimals)))

      if (progress < 1) {
        frameRef.current = requestAnimationFrame(animate)
      } else {
        startRef.current = null
      }
    }

    startRef.current = null
    frameRef.current = requestAnimationFrame(animate)

    return () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current)
    }
  }, [target, duration, decimals])

  return current
}

// Mini sparkline SVG
function Sparkline({ data, color }: { data: SparklineData[]; color: string }) {
  if (!data || data.length < 2) return null

  const width = 80
  const height = 28
  const values = data.map((d) => d.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1

  const points = values.map((v, i) => {
    const x = (i / (values.length - 1)) * width
    const y = height - ((v - min) / range) * (height - 4) - 2
    return `${x},${y}`
  })

  const pathD = `M ${points.join(' L ')}`

  return (
    <svg width={width} height={height} className="opacity-70">
      <defs>
        <linearGradient id={`spark-gradient-${color.replace('#', '')}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.4" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path
        d={`${pathD} L ${width},${height} L 0,${height} Z`}
        fill={`url(#spark-gradient-${color.replace('#', '')})`}
      />
      <path
        d={pathD}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export default function StatCard({
  title,
  value,
  unit,
  color = 'cyan',
  icon,
  change,
  changeLabel,
  sparkline,
  prefix,
  suffix,
  loading = false,
  className,
  decimals = 0,
}: StatCardProps) {
  const animatedValue = useCountUp(value, 1000, decimals)
  const conf = colorConfig[color]

  const formattedValue = animatedValue >= 1000000
    ? `${(animatedValue / 1000000).toFixed(1)}M`
    : animatedValue >= 1000
    ? `${(animatedValue / 1000).toFixed(1)}K`
    : animatedValue.toFixed(decimals)

  return (
    <motion.div
      className={clsx(
        'glass-card border p-5 relative overflow-hidden transition-all duration-200',
        conf.border,
        className
      )}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      {/* Gradient de fundo no canto */}
      <div
        className={clsx('absolute -top-8 -right-8 w-24 h-24 rounded-full blur-2xl opacity-20', conf.gradient, 'bg-gradient-radial')}
      />

      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          {icon && (
            <div className={clsx('p-2 rounded-lg', conf.iconBg)}>
              <span className={clsx(conf.text, 'block')}>
                {icon}
              </span>
            </div>
          )}
          <span className="text-text-secondary text-sm font-medium tracking-wide">{title}</span>
        </div>
        {sparkline && <Sparkline data={sparkline} color={conf.spark} />}
      </div>

      {/* Valor principal */}
      {loading ? (
        <div className="h-9 bg-bg-surface rounded animate-pulse w-3/4" />
      ) : (
        <div className="flex items-end gap-1">
          {prefix && <span className={clsx('text-lg font-mono font-medium', conf.text)}>{prefix}</span>}
          <span className={clsx('text-3xl font-mono font-bold tracking-tight', conf.text)}>
            {formattedValue}
          </span>
          {suffix || unit ? (
            <span className="text-text-muted text-sm font-mono mb-1">{suffix || unit}</span>
          ) : null}
        </div>
      )}

      {/* Variação */}
      {change !== undefined && !loading && (
        <div className="mt-2 flex items-center gap-1">
          <span
            className={clsx(
              'text-xs font-mono font-medium',
              change >= 0 ? 'text-neon-green' : 'text-neon-red'
            )}
          >
            {change >= 0 ? '↑' : '↓'} {Math.abs(change).toFixed(1)}%
          </span>
          {changeLabel && (
            <span className="text-text-muted text-xs">{changeLabel}</span>
          )}
        </div>
      )}
    </motion.div>
  )
}
