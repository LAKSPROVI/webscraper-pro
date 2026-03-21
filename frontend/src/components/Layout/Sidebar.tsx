import React from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  LayoutDashboard,
  Briefcase,
  Database,
  Bug,
  Calendar,
  Monitor,
  ChevronRight,
  Wifi,
  WifiOff,
  Activity,
} from 'lucide-react'
import clsx from 'clsx'
import { useAppStore } from '../../stores/appStore'
import { useWebSocket } from '../../hooks/useWebSocket'

interface NavItem {
  path: string
  label: string
  icon: React.ReactNode
  badge?: number
  external?: boolean
}

const navItems: NavItem[] = [
  { path: '/', label: 'Dashboard', icon: <LayoutDashboard size={18} /> },
  { path: '/jobs', label: 'Jobs', icon: <Briefcase size={18} /> },
  { path: '/data', label: 'Explorador', icon: <Database size={18} /> },
  { path: '/spiders', label: 'Spiders', icon: <Bug size={18} /> },
  { path: '/schedule', label: 'Agendamentos', icon: <Calendar size={18} /> },
  { path: '/monitoring', label: 'Monitoramento', icon: <Monitor size={18} /> },
]

function SpiderLogo() {
  return (
    <div className="flex items-center gap-3 px-4 py-5 border-b border-border-dim">
      {/* Ícone de aranha animado */}
      <div className="relative w-9 h-9 spider-float">
        <div
          className="w-9 h-9 rounded-xl flex items-center justify-center"
          style={{
            background: 'linear-gradient(135deg, rgba(0,212,255,0.2) 0%, rgba(124,58,237,0.2) 100%)',
            border: '1px solid rgba(0,212,255,0.4)',
            boxShadow: '0 0 16px rgba(0,212,255,0.2)',
          }}
        >
          <Bug size={20} className="text-neon-cyan" />
        </div>
        {/* Pulsing ring */}
        <div
          className="absolute inset-0 rounded-xl animate-ping"
          style={{
            border: '1px solid rgba(0,212,255,0.3)',
            animationDuration: '3s',
          }}
        />
      </div>
      <div>
        <h1 className="text-text-primary font-bold text-base tracking-tight leading-none">
          Web<span className="text-neon-cyan">Scraper</span>
        </h1>
        <p className="text-text-muted text-xs mt-0.5 font-mono">v2.0.0 · Sistema</p>
      </div>
    </div>
  )
}

function SystemStatusIndicator() {
  const { status: wsStatus } = useWebSocket()
  const { systemStatus, activeJobsCount } = useAppStore()

  const isConnected = wsStatus === 'connected'

  return (
    <div className="mx-3 mb-2 p-3 rounded-lg bg-bg-card border border-border-dim">
      {/* API Status */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-text-muted text-xs font-mono">Sistema</span>
        <div className="flex items-center gap-1.5">
          {isConnected ? (
            <Wifi size={12} className="text-neon-green" />
          ) : (
            <WifiOff size={12} className="text-neon-amber animate-pulse" />
          )}
          <span className={clsx('text-xs font-mono', isConnected ? 'text-neon-green' : 'text-neon-amber')}>
            {isConnected ? 'Online' : 'Reconectando...'}
          </span>
        </div>
      </div>

      {/* Serviços */}
      <div className="grid grid-cols-3 gap-1">
        {[
          { label: 'API', status: systemStatus.api },
          { label: 'DB', status: systemStatus.db },
          { label: 'Redis', status: systemStatus.redis },
        ].map(({ label, status }) => (
          <div key={label} className="flex flex-col items-center gap-0.5">
            <div
              className={clsx(
                'w-2 h-2 rounded-full',
                status === 'online' ? 'live-dot' : status === 'degraded' ? 'bg-neon-amber animate-pulse' : 'bg-neon-red'
              )}
            />
            <span className="text-text-muted text-xs font-mono">{label}</span>
          </div>
        ))}
      </div>

      {/* Jobs ativos */}
      {activeJobsCount > 0 && (
        <div className="mt-2 pt-2 border-t border-border-dim flex items-center gap-1.5">
          <Activity size={10} className="text-neon-cyan animate-pulse" />
          <span className="text-neon-cyan text-xs font-mono">
            {activeJobsCount} job{activeJobsCount !== 1 ? 's' : ''} ativo{activeJobsCount !== 1 ? 's' : ''}
          </span>
        </div>
      )}
    </div>
  )
}

export default function Sidebar() {
  const location = useLocation()
  const { activeJobsCount } = useAppStore()

  return (
    <aside
      className="fixed left-0 top-0 h-screen w-56 flex flex-col z-sidebar overflow-hidden"
      style={{
        background: 'rgba(5, 8, 16, 0.95)',
        borderRight: '1px solid rgba(255,255,255,0.06)',
        backdropFilter: 'blur(12px)',
      }}
    >
      {/* Logo */}
      <SpiderLogo />

      {/* Navegação */}
      <nav className="flex-1 px-3 py-3 overflow-y-auto">
        <div className="space-y-1">
          {navItems.map((item) => {
            const isActive = item.path === '/'
              ? location.pathname === '/'
              : location.pathname.startsWith(item.path)

            const hasActiveBadge = item.path === '/jobs' && activeJobsCount > 0

            return (
              <NavLink
                key={item.path}
                to={item.path}
                className={clsx(
                  'flex items-center gap-3 px-3 py-2.5 rounded-lg',
                  'transition-all duration-200 ease-in-out',
                  'group relative overflow-hidden',
                  isActive
                    ? 'bg-neon-cyan-dim text-neon-cyan border border-neon-cyan-mid'
                    : 'text-text-secondary hover:text-text-primary hover:bg-bg-surface'
                )}
                style={isActive ? {
                  boxShadow: '0 0 12px rgba(0,212,255,0.1)',
                } : undefined}
              >
                {/* Scan effect no item ativo */}
                {isActive && (
                  <div
                    className="absolute inset-0 pointer-events-none"
                    style={{
                      background: 'linear-gradient(90deg, transparent 0%, rgba(0,212,255,0.05) 50%, transparent 100%)',
                      animation: 'scan-line 3s linear infinite',
                    }}
                  />
                )}

                {/* Ícone */}
                <span className={clsx(
                  'relative z-10 transition-all duration-200',
                  isActive ? 'text-neon-cyan' : 'text-text-muted group-hover:text-text-secondary'
                )}>
                  {item.icon}
                </span>

                {/* Label */}
                <span className="relative z-10 text-sm font-medium flex-1">
                  {item.label}
                </span>

                {/* Badge */}
                <AnimatePresence>
                  {hasActiveBadge && (
                    <motion.span
                      initial={{ scale: 0 }}
                      animate={{ scale: 1 }}
                      exit={{ scale: 0 }}
                      className="relative z-10 min-w-[18px] h-[18px] rounded-full bg-neon-cyan text-bg-base text-xs font-bold font-mono flex items-center justify-center px-1"
                      style={{ boxShadow: '0 0 8px rgba(0,212,255,0.6)' }}
                    >
                      {activeJobsCount > 99 ? '99+' : activeJobsCount}
                    </motion.span>
                  )}
                </AnimatePresence>

                {/* Arrow para item ativo */}
                {isActive && (
                  <ChevronRight size={14} className="relative z-10 text-neon-cyan opacity-60" />
                )}
              </NavLink>
            )
          })}
        </div>
      </nav>

      {/* Status do Sistema */}
      <div className="mt-auto">
        <SystemStatusIndicator />

        {/* Footer */}
        <div className="px-4 py-3 border-t border-border-dim">
          <p className="text-text-muted text-xs font-mono text-center">
            © 2024 WebScraper Pro
          </p>
        </div>
      </div>
    </aside>
  )
}
