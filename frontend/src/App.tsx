import React, { useEffect } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { useAppStore } from './stores/appStore'
import { useHealthCheck } from './hooks/useApi'
import Sidebar from './components/Layout/Sidebar'
import TopBar from './components/Layout/TopBar'
import Dashboard from './pages/Dashboard'
import Jobs from './pages/Jobs'
import DataExplorer from './pages/DataExplorer'
import Spiders from './pages/Spiders'
import Schedule from './pages/Schedule'

// Página de Monitoramento
function MonitoringPage() {
  const links = [
    { label: 'Grafana', url: 'http://localhost:3001', icon: '📊', desc: 'Dashboards e métricas' },
    { label: 'Flower (Celery)', url: 'http://localhost:5555', icon: '🌸', desc: 'Monitor de tarefas' },
    { label: 'Prometheus', url: 'http://localhost:9090', icon: '🔥', desc: 'Métricas de sistema' },
    { label: 'Loki', url: 'http://localhost:3100', icon: '📋', desc: 'Logs centralizados' },
  ]
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {links.map((link) => (
          <a
            key={link.label}
            href={link.url}
            target="_blank"
            rel="noopener noreferrer"
            className="glass-card border border-border-dim hover:border-neon-cyan-mid p-5 flex items-center gap-4 transition-all duration-200 hover:shadow-glow-cyan group"
          >
            <div className="text-3xl">{link.icon}</div>
            <div>
              <h3 className="text-text-primary font-semibold group-hover:text-neon-cyan transition-colors">{link.label}</h3>
              <p className="text-text-muted text-sm">{link.desc}</p>
              <p className="text-neon-cyan text-xs font-mono mt-1">{link.url}</p>
            </div>
          </a>
        ))}
      </div>
    </div>
  )
}

// Layout wrapper
function AppLayout() {
  const { data: health } = useHealthCheck()
  const { setSystemStatus, setApiOnline } = useAppStore()

  useEffect(() => {
    if (health) {
      setSystemStatus({
        api: health.api,
        db: health.db,
        redis: health.redis,
      })
      setApiOnline(health.api === 'online')
    }
  }, [health, setSystemStatus, setApiOnline])

  return (
    <div className="min-h-screen bg-dot-grid" style={{ backgroundColor: '#050810' }}>
      <Sidebar />
      <TopBar />
      <main
        className="relative z-10"
        style={{ marginLeft: '224px', paddingTop: '56px' }}
      >
        <div className="p-6 max-w-[1600px] mx-auto">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/jobs" element={<Jobs />} />
            <Route path="/data" element={<DataExplorer />} />
            <Route path="/spiders" element={<Spiders />} />
            <Route path="/schedule" element={<Schedule />} />
            <Route path="/monitoring" element={<MonitoringPage />} />
          </Routes>
        </div>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppLayout />
    </BrowserRouter>
  )
}
