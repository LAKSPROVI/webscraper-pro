import React from 'react'
import { motion } from 'framer-motion'
import clsx from 'clsx'

type NeonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'success'
type NeonSize = 'sm' | 'md' | 'lg' | 'xl'

interface NeonButtonProps {
  children: React.ReactNode
  onClick?: () => void
  variant?: NeonVariant
  size?: NeonSize
  disabled?: boolean
  loading?: boolean
  className?: string
  type?: 'button' | 'submit' | 'reset'
  icon?: React.ReactNode
  fullWidth?: boolean
}

const variantClasses: Record<NeonVariant, string> = {
  primary: [
    'bg-neon-cyan-dim border-neon-cyan-mid text-neon-cyan',
    'hover:bg-opacity-30 hover:shadow-glow-cyan-sm hover:border-neon-cyan',
  ].join(' '),
  secondary: [
    'bg-neon-purple-dim border-neon-purple-mid text-purple-300',
    'hover:bg-opacity-30 hover:shadow-glow-purple hover:border-neon-purple',
  ].join(' '),
  ghost: [
    'bg-transparent border-border-mid text-text-secondary',
    'hover:border-neon-cyan-mid hover:text-neon-cyan hover:bg-neon-cyan-dim',
  ].join(' '),
  danger: [
    'bg-neon-red-dim border-neon-red-dim text-neon-red',
    'hover:bg-opacity-30 hover:shadow-glow-red hover:border-neon-red',
  ].join(' '),
  success: [
    'bg-neon-green-dim border-neon-green-dim text-neon-green',
    'hover:bg-opacity-30 hover:shadow-glow-green hover:border-neon-green',
  ].join(' '),
}

const sizeClasses: Record<NeonSize, string> = {
  sm: 'px-3 py-1.5 text-xs gap-1.5',
  md: 'px-4 py-2 text-sm gap-2',
  lg: 'px-5 py-2.5 text-sm gap-2',
  xl: 'px-6 py-3 text-base gap-2.5',
}

export default function NeonButton({
  children,
  onClick,
  variant = 'primary',
  size = 'md',
  disabled = false,
  loading = false,
  className,
  type = 'button',
  icon,
  fullWidth = false,
}: NeonButtonProps) {
  return (
    <motion.button
      type={type}
      onClick={onClick}
      disabled={disabled || loading}
      whileHover={{ scale: disabled || loading ? 1 : 1.02 }}
      whileTap={{ scale: disabled || loading ? 1 : 0.98 }}
      className={clsx(
        'inline-flex items-center justify-center rounded-lg border font-medium',
        'transition-all duration-200 ease-in-out',
        'focus:outline-none focus:ring-2 focus:ring-neon-cyan focus:ring-offset-2 focus:ring-offset-bg-base',
        'font-sans tracking-wide',
        variantClasses[variant],
        sizeClasses[size],
        fullWidth && 'w-full',
        (disabled || loading) && 'opacity-50 cursor-not-allowed pointer-events-none',
        className
      )}
    >
      {loading ? (
        <span
          className="inline-block rounded-full flex-shrink-0"
          style={{
            width: size === 'sm' ? '12px' : '14px',
            height: size === 'sm' ? '12px' : '14px',
            border: '2px solid currentColor',
            borderTopColor: 'transparent',
            animation: 'spin 0.8s linear infinite',
          }}
        />
      ) : icon ? (
        <span className="flex-shrink-0">{icon}</span>
      ) : null}
      {children}
    </motion.button>
  )
}
