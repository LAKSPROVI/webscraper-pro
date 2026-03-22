import React, { useState } from 'react'
import { useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Plus, Zap, CheckCircle, AlertCircle, Server } from 'lucide-react'
import clsx from 'clsx'
import { useAppStore } from '../../stores/appStore'
import NeonButton from '../ui/NeonButton'
import { useScrape } from '../../hooks/useApi'

interface NewScrapeModalProps {
  onClose: () => void
}

const pageNames: Record<string, string> = {
  '/': 'Dashboard',
  '/jobs': 'Gerenciador de Jobs',
  '/data': 'Explorador de Dados',
  '/spiders': 'Configuração de Spiders',
  '/schedule': 'Agendamentos',
  '/monitoring': 'Monitoramento',
}

function NewScrapeModal({ onClose }: NewScrapeModalProps) {
  const [url, setUrl] = useState('')
  const [spiderType, setSpiderType] = useState('generic')
  const [renderJs, setRenderJs] = useState(false)
  const [useProxy, setUseProxy] = useState(false)
  const [crawlDepth, setCrawlDepth] = useState(1)
  const [urlError, setUrlError] = useState('')

  const { mutate: scrape, isPending } = useScrape()

  const validateUrl = (value: string) => {
    try {
      new URL(value)
      setUrlError('')
      return true
    } catch {
      setUrlError('URL inválida. Ex: https://example.com')
      return false
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!validateUrl(url)) return
    scrape({
      url,
      spider_type: spiderType,
      render_js: renderJs,
      use_proxy: useProxy,
      crawl_depth: crawlDepth,
    }, {
      onSuccess: () => onClose(),
    })
  }

  const spiderTypes = [
    { value: 'generic', label: 'Genérico', icon: '🕸️', desc: 'Extração de conteúdo geral' },
    { value: 'news', label: 'Notícias', icon: '📰', desc: 'Artigos e notícias' },
    { value: 'article', label: 'Artigo', icon: '📄', desc: 'Artigos detalhados' },
    { value: 'ecommerce', label: 'E-commerce', icon: '🛒', desc: 'Produtos e preços' },
  ]

  return (
    <div className="fixed inset-0 z-modal flex items-center justify-center modal-overlay" onClick={onClose}>
      <motion.div
        className="w-full max-w-lg mx-4"
        initial={{ opacity: 0, scale: 0.9, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.9, y: 20 }}
        transition={{ type: 'spring', stiffness: 300, damping: 25 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className="glass-card border border-neon-cyan-mid rounded-xl overflow-hidden"
          style={{ boxShadow: '0 0 40px rgba(0,212,255,0.1), 0 20px 60px rgba(0,0,0,0.5)' }}
        >
          {/* Header */}
          <div className="px-6 py-4 border-b border-border-dim bg-neon-cyan-dim">
            <div className="flex items-center gap-3">
              <Zap size={18} className="text-neon-cyan" />
              <h2 className="text-text-primary font-semibold text-base">Novo Scraping</h2>
            </div>
            <p className="text-text-muted text-xs font-mono mt-1">Configure e inicie uma nova coleta de dados</p>
          </div>

          {/* Formulário */}
          <form onSubmit={handleSubmit} className="p-6 space-y-5">
            {/* URL */}
            <div>
              <label className="block text-text-secondary text-xs font-medium mb-1.5 font-mono">
                URL ALVO *
              </label>
              <input
                type="text"
                value={url}
                onChange={(e) => {
                  setUrl(e.target.value)
                  if (e.target.value) validateUrl(e.target.value)
                }}
                placeholder="https://exemplo.com/pagina"
                className={clsx(
                  'input-neon w-full px-4 py-2.5 text-sm',
                  urlError && 'border-neon-red'
                )}
                autoFocus
              />
              {urlError && (
                <p className="mt-1 text-neon-red text-xs font-mono">{urlError}</p>
              )}
            </div>

            {/* Spider Type */}
            <div>
              <label className="block text-text-secondary text-xs font-medium mb-2 font-mono">
                TIPO DE SPIDER
              </label>
              <div className="grid grid-cols-2 gap-2">
                {spiderTypes.map((s) => (
                  <button
                    key={s.value}
                    type="button"
                    onClick={() => setSpiderType(s.value)}
                    className={clsx(
                      'p-3 rounded-lg border text-left transition-all duration-200',
                      spiderType === s.value
                        ? 'border-neon-cyan-mid bg-neon-cyan-dim'
                        : 'border-border-dim bg-bg-card hover:border-border-mid'
                    )}
                  >
                    <div className="text-lg mb-1">{s.icon}</div>
                    <div className="text-text-primary text-xs font-medium">{s.label}</div>
                    <div className="text-text-muted text-xs">{s.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Opções */}
            <div className="grid grid-cols-3 gap-4">
              {/* Render JS */}
              <div>
                <label className="block text-text-secondary text-xs font-medium mb-2 font-mono">
                  RENDERIZAR JS
                </label>
                <button
                  type="button"
                  onClick={() => setRenderJs(!renderJs)}
                  className={clsx(
                    'flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-mono transition-all duration-200 w-full',
                    renderJs
                      ? 'border-neon-cyan-mid bg-neon-cyan-dim text-neon-cyan'
                      : 'border-border-dim bg-bg-card text-text-muted'
                  )}
                >
                  <div className={clsx('w-4 h-4 rounded border flex items-center justify-center', renderJs ? 'border-neon-cyan bg-neon-cyan' : 'border-border-mid')}>
                    {renderJs && <span className="text-bg-base text-xs">✓</span>}
                  </div>
                  {renderJs ? 'Ativado' : 'Desativado'}
                </button>
              </div>

              {/* Use Proxy */}
              <div>
                <label className="block text-text-secondary text-xs font-medium mb-2 font-mono">
                  USAR PROXY
                </label>
                <button
                  type="button"
                  onClick={() => setUseProxy(!useProxy)}
                  className={clsx(
                    'flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-mono transition-all duration-200 w-full',
                    useProxy
                      ? 'border-neon-purple-mid bg-neon-purple-dim text-neon-purple'
                      : 'border-border-dim bg-bg-card text-text-muted'
                  )}
                >
                  <div className={clsx('w-4 h-4 rounded border flex items-center justify-center', useProxy ? 'border-neon-purple bg-neon-purple' : 'border-border-mid')}>
                    {useProxy && <span className="text-bg-base text-xs">✓</span>}
                  </div>
                  {useProxy ? 'Ativado' : 'Desativado'}
                </button>
              </div>

              {/* Crawl Depth */}
              <div>
                <label className="block text-text-secondary text-xs font-medium mb-2 font-mono">
                  PROFUNDIDADE: <span className="text-neon-cyan">{crawlDepth}</span>
                </label>
                <input
                  type="range"
                  min={1}
                  max={5}
                  value={crawlDepth}
                  onChange={(e) => setCrawlDepth(Number(e.target.value))}
                  className="w-full h-2 rounded-full appearance-none bg-bg-surface cursor-pointer"
                  style={{
                    accentColor: '#00d4ff',
                  }}
                />
              </div>
            </div>

            {/* Buttons */}
            <div className="flex gap-3 pt-2">
              <NeonButton
                variant="ghost"
                onClick={onClose}
                className="flex-1"
              >
                Cancelar
              </NeonButton>
              <NeonButton
                type="submit"
                variant="primary"
                loading={isPending}
                className="flex-1"
                icon={<Zap size={14} />}
              >
                {isPending ? 'Iniciando...' : 'Iniciar Scraping'}
              </NeonButton>
            </div>
          </form>
        </div>
      </motion.div>
    </div>
  )
}

export default function TopBar() {
  const location = useLocation()
  const { activeJobsCount, itemsPerHour, systemStatus } = useAppStore()
  const [showModal, setShowModal] = useState(false)

  const pageName = pageNames[location.pathname] || 'Dashboard'

  return (
    <>
      <header
        className="fixed top-0 left-56 right-0 h-14 flex items-center px-6 z-topbar"
        style={{
          background: 'rgba(5, 8, 16, 0.9)',
          borderBottom: '1px solid rgba(255,255,255,0.06)',
          backdropFilter: 'blur(12px)',
        }}
      >
        {/* Título da Página */}
        <div className="flex-1">
          <h2 className="text-text-primary font-semibold text-base">{pageName}</h2>
        </div>

        {/* Stats em tempo real */}
        <div className="hidden md:flex items-center gap-4 mr-4">
          {activeJobsCount > 0 && (
            <div className="flex items-center gap-1.5">
              <div className="live-dot" />
              <span className="text-neon-green text-xs font-mono">
                {activeJobsCount} rodando
              </span>
            </div>
          )}
          {itemsPerHour > 0 && (
            <div className="flex items-center gap-1.5">
              <Zap size={12} className="text-neon-amber" />
              <span className="text-text-secondary text-xs font-mono">
                {itemsPerHour.toLocaleString('pt-BR')} items/h
              </span>
            </div>
          )}

          {/* Indicadores de Saúde */}
          <div className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-bg-card border border-border-dim">
            <Server size={12} className="text-text-muted" />
            {[
              { label: 'API', status: systemStatus.api },
              { label: 'DB', status: systemStatus.db },
              { label: 'Redis', status: systemStatus.redis },
            ].map(({ label, status }) => (
              <div key={label} className="flex items-center gap-1">
                <div
                  className={clsx(
                    'w-1.5 h-1.5 rounded-full',
                    status === 'online' ? 'bg-neon-green' : status === 'degraded' ? 'bg-neon-amber animate-pulse' : 'bg-neon-red'
                  )}
                />
                <span className="text-text-muted text-xs font-mono">{label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Botão Novo Scrape */}
        <NeonButton
          onClick={() => setShowModal(true)}
          size="sm"
          icon={<Plus size={14} />}
        >
          Novo Scrape
        </NeonButton>
      </header>

      {/* Modal */}
      <AnimatePresence>
        {showModal && (
          <NewScrapeModal onClose={() => setShowModal(false)} />
        )}
      </AnimatePresence>
    </>
  )
}
