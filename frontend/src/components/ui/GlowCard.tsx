import React from 'react'
import { motion } from 'framer-motion'
import clsx from 'clsx'

type GlowColor = 'cyan' | 'purple' | 'green' | 'amber' | 'red'

interface GlowCardProps {
  children: React.ReactNode
  className?: string
  color?: GlowColor
  hover?: boolean
  animated?: boolean
  onClick?: () => void
}

const colorMap: Record<GlowColor, string> = {
  cyan: 'border-neon-cyan-dim hover:border-neon-cyan-mid hover:shadow-glow-cyan',
  purple: 'border-neon-purple-dim hover:border-neon-purple-mid hover:shadow-glow-purple',
  green: 'border-neon-green-dim hover:border-neon-green-mid hover:shadow-glow-green',
  amber: 'border-neon-amber-dim hover:shadow-glow-amber',
  red: 'border-neon-red-dim hover:shadow-glow-red',
}

export default function GlowCard({
  children,
  className,
  color = 'cyan',
  hover = true,
  animated = false,
  onClick,
}: GlowCardProps) {
  const baseClasses = clsx(
    'glass-card border relative overflow-hidden',
    colorMap[color],
    hover && 'transition-all duration-200',
    hover && onClick && 'cursor-pointer',
    animated && 'neon-border',
    className
  )

  if (onClick || animated) {
    return (
      <motion.div
        className={baseClasses}
        onClick={onClick}
        whileHover={hover ? { y: -2, scale: 1.005 } : undefined}
        transition={{ type: 'spring', stiffness: 300, damping: 20 }}
      >
        {children}
      </motion.div>
    )
  }

  return (
    <div className={baseClasses}>
      {children}
    </div>
  )
}
