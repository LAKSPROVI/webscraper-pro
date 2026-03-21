import React, { useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Search, Download, X, ExternalLink, Filter,
  Clock, Globe, BarChart2,
} from 'lucide-react'
import { format } from 'date-fns'
import { ptBR } from 'date-fns/locale'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import clsx from 'clsx'
import { useData } from '../hooks/useApi'
import type { ScrapedItem } from '../stores/appStore'
import GlowCard from '../components/ui/GlowCard'
import NeonButton from '../components/ui/NeonButton'
import { PageLoader } from '../components/ui/LoadingSpinner'

// Debounce hook
function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = React.useState(value)
  React.useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}

// Highlight de termos no texto
function HighlightText({ text, query }: { text: string; query: string }) {
  if (!query.trim()) return <span>{text}</span>

  const parts = text.split(new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'))
  return (
    <span>
      {parts.map((part, i) =>
        part.toLowerCase() === query.toLowerCase() ? (
          <mark
            key={i}
            className="bg-neon-cyan-dim text-neon-cyan px-0.5 rounded"
          >
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </span>
  )
}

// Mock data
const mockItems: ScrapedItem[] = Array.from({ length: 12 }, (_, i) => ({
  id: `item-${i + 1}`,
  job_id: `job-${i + 1}`,
  url: `https://${['reddit.com', 'medium.com', 'hackernews.com', 'github.com'][i % 4]}/article/${i * 100}`,
  title: [
    'Como construir um sistema de webscraping escalável com Python',
    'Machine Learning em Produção: Lições Aprendidas',
    'A nova abordagem para arquitetura de microsserviços',
    'Rust vs Go: Qual escolher para sistemas de alta performance',
    'Docker e Kubernetes: O guia definitivo para iniciantes',
    'APIs REST vs GraphQL: Quando usar cada um',
    'Inteligência Artificial no desenvolvimento de software',
    'DevOps em 2024: Tendências e melhores práticas',
    'Segurança em aplicações web: Os 10 principais riscos',
    'TypeScript 5.0: Novas funcionalidades e melhorias',
    'PostgreSQL tuning: Como otimizar queries complexas',
    'React Server Components: O futuro do desenvolvimento web',
  ][i],
  content: 'Neste artigo, exploramos as melhores práticas e padrões de design para construir sistemas modernos e escaláveis...',
  domain: ['reddit.com', 'medium.com', 'hackernews.com', 'github.com'][i % 4],
  spider_type: ['generic', 'news', 'article'][i % 3],
  scraped_at: new Date(Date.now() - i * 7200000).toISOString(),
  metadata: { word_count: Math.floor(Math.random() * 3000 + 500), reading_time: Math.floor(Math.random() * 15 + 3) },
}))

const domainColors = ['#00d4ff', '#7c3aed', '#00ff88', '#ffb800', '#ff3366']

// Modal de detalhe do item
function ItemDetailModal({ item, query, onClose }: { item: ScrapedItem; query: string; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-modal flex items-center justify-center modal-overlay" onClick={onClose}>
      <motion.div
        className="w-full max-w-2xl mx-4 max-h-[80vh] overflow-y-auto"
        initial={{ opacity: 0, scale: 0.9, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.9, y: 20 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="glass-card border border-neon-cyan-mid rounded-xl overflow-hidden">
          <div className="p-4 border-b border-border-dim flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h3 className="text-text-primary font-semibold text-sm leading-tight">
                <HighlightText text={item.title || 'Sem título'} query={query} />
              </h3>
              <div className="flex items-center gap-2 mt-1.5">
                <Globe size={11} className="text-text-muted" />
                <a href={item.url} target="_blank" rel="noopener noreferrer" className="text-neon-cyan text-xs font-mono hover:underline truncate">
                  {item.url}
                </a>
              </div>
            </div>
            <button onClick={onClose} className="text-text-muted hover:text-text-primary p-1 flex-shrink-0">
              <X size={16} />
            </button>
          </div>

          <div className="p-5 space-y-4">
            {/* Metadados */}
            <div className="grid grid-cols-3 gap-3">
              {[
                { label: 'Domínio', value: item.domain },
                { label: 'Spider', value: item.spider_type },
                { label: 'Data', value: format(new Date(item.scraped_at), "dd/MM/yy HH:mm", { locale: ptBR }) },
              ].map(({ label, value }) => (
                <div key={label} className="bg-bg-surface rounded-lg p-3">
                  <p className="text-text-muted text-xs font-mono mb-1">{label}</p>
                  <p className="text-text-primary text-xs font-medium">{value}</p>
                </div>
              ))}
            </div>

            {/* Conteúdo */}
            <div>
              <p className="text-text-muted text-xs font-mono mb-2">CONTEÚDO</p>
              <div className="bg-bg-surface rounded-lg p-4 text-text-secondary text-sm leading-relaxed">
                <HighlightText text={item.content || 'Sem conteúdo disponível'} query={query} />
              </div>
            </div>

            {/* Metadados extras */}
            {item.metadata && (
              <div>
                <p className="text-text-muted text-xs font-mono mb-2">METADADOS</p>
                <div className="bg-bg-surface rounded-lg p-3 font-mono text-xs text-text-secondary">
                  {JSON.stringify(item.metadata, null, 2)}
                </div>
              </div>
            )}
          </div>
        </div>
      </motion.div>
    </div>
  )
}

// Card de resultado
function ResultCard({ item, query, onClick }: { item: ScrapedItem; query: string; onClick: () => void }) {
  const wordCount = item.metadata?.word_count as number | undefined
  const readingTime = item.metadata?.reading_time as number | undefined

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card border border-border-dim hover:border-neon-cyan-dim p-4 cursor-pointer transition-all duration-200 hover:shadow-glow-cyan group"
      onClick={onClick}
    >
      {/* Header */}
      <div className="flex items-start gap-3 mb-2">
        <div className="w-6 h-6 rounded bg-bg-surface flex items-center justify-center flex-shrink-0 mt-0.5">
          <Globe size={12} className="text-text-muted" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-text-muted text-xs font-mono mb-1">{item.domain}</p>
          <h4 className="text-text-primary text-sm font-semibold leading-tight group-hover:text-neon-cyan transition-colors">
            <HighlightText text={item.title || 'Sem título'} query={query} />
          </h4>
        </div>
      </div>

      {/* Snippet */}
      <p className="text-text-secondary text-xs leading-relaxed line-clamp-2 mb-3">
        <HighlightText text={item.content?.slice(0, 150) + '...' || ''} query={query} />
      </p>

      {/* Footer */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={clsx(
            'px-2 py-0.5 rounded-full text-xs font-mono border',
            item.spider_type === 'news' ? 'text-neon-purple bg-neon-purple-dim border-neon-purple-dim' :
            item.spider_type === 'article' ? 'text-neon-green bg-neon-green-dim border-neon-green-dim' :
            'text-neon-cyan bg-neon-cyan-dim border-neon-cyan-dim'
          )}>
            {item.spider_type}
          </span>
          {wordCount && (
            <span className="text-text-muted text-xs font-mono">{wordCount.toLocaleString('pt-BR')} palavras</span>
          )}
          {readingTime && (
            <span className="text-text-muted text-xs font-mono flex items-center gap-1">
              <Clock size={10} />
              {readingTime}min
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <Clock size={10} className="text-text-muted" />
          <span className="text-text-muted text-xs font-mono">
            {format(new Date(item.scraped_at), 'dd/MM HH:mm', { locale: ptBR })}
          </span>
        </div>
      </div>
    </motion.div>
  )
}

export default function DataExplorer() {
  const [query, setQuery] = useState('')
  const [domainFilter, setDomainFilter] = useState('')
  const [selectedItem, setSelectedItem] = useState<ScrapedItem | null>(null)
  const [page, setPage] = useState(1)
  const [isExporting, setIsExporting] = useState(false)

  const debouncedQuery = useDebounce(query, 400)

  const startTime = React.useRef(Date.now())
  const [searchTime, setSearchTime] = React.useState(0)

  const { data, isLoading } = useData({
    q: debouncedQuery || undefined,
    domain: domainFilter || undefined,
    page,
    limit: 12,
  })

  React.useEffect(() => {
    if (!isLoading) {
      setSearchTime(Date.now() - startTime.current)
      startTime.current = Date.now()
    }
  }, [isLoading, debouncedQuery])

  const displayItems = data?.items || mockItems
  const total = data?.total || mockItems.length

  // Stats por domínio (mock)
  const domainStats = [
    { name: 'reddit.com', value: 35 },
    { name: 'medium.com', value: 28 },
    { name: 'hackernews.com', value: 20 },
    { name: 'github.com', value: 17 },
  ]

  const handleExport = async (format: 'json' | 'csv') => {
    setIsExporting(true)
    await new Promise(r => setTimeout(r, 1500))
    setIsExporting(false)
    // Na versão real: chamar API e fazer download
    const blob = new Blob([JSON.stringify(displayItems, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `webscraper-export-${Date.now()}.${format}`
    a.click()
  }

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Busca principal */}
      <GlowCard color="cyan" className="p-4">
        <div className="relative">
          <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="🔍 Buscar em todos os dados coletados..."
            className="input-neon w-full pl-12 pr-4 py-3 text-base"
          />
          {query && (
            <button
              onClick={() => setQuery('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
            >
              <X size={16} />
            </button>
          )}
        </div>

        {/* Info de resultado */}
        {(debouncedQuery || isLoading) && (
          <div className="mt-2 flex items-center justify-between">
            {isLoading ? (
              <span className="text-text-muted text-xs font-mono animate-pulse">Buscando...</span>
            ) : (
              <span className="text-text-secondary text-xs font-mono">
                Encontrado <span className="text-neon-cyan font-bold">{total.toLocaleString('pt-BR')}</span> resultado{total !== 1 ? 's' : ''} em <span className="text-neon-cyan">{searchTime}ms</span>
              </span>
            )}
          </div>
        )}
      </GlowCard>

      {/* Layout principal */}
      <div className="grid grid-cols-1 xl:grid-cols-4 gap-4">
        {/* Filtros laterais */}
        <div className="xl:col-span-1 space-y-4">
          {/* Filtro por domínio */}
          <GlowCard color="purple" className="p-4">
            <h3 className="text-text-secondary text-xs font-mono font-semibold mb-3 uppercase tracking-widest">
              FILTROS
            </h3>
            <div className="space-y-3">
              <div>
                <label className="text-text-muted text-xs font-mono block mb-1.5">Domínio</label>
                <input
                  type="text"
                  value={domainFilter}
                  onChange={(e) => setDomainFilter(e.target.value)}
                  placeholder="ex: reddit.com"
                  className="input-neon w-full px-3 py-2 text-xs"
                />
              </div>
            </div>
          </GlowCard>

          {/* Distribuição por domínio */}
          <GlowCard color="amber" className="p-4">
            <h3 className="text-text-secondary text-xs font-mono font-semibold mb-3 uppercase tracking-widest flex items-center gap-2">
              <BarChart2 size={12} />
              DISTRIBUIÇÃO
            </h3>
            <ResponsiveContainer width="100%" height={140}>
              <PieChart>
                <Pie
                  data={domainStats}
                  cx="50%"
                  cy="50%"
                  innerRadius={35}
                  outerRadius={55}
                  dataKey="value"
                  strokeWidth={0}
                >
                  {domainStats.map((_, i) => (
                    <Cell key={i} fill={domainColors[i % domainColors.length]} opacity={0.8} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    background: '#0a0e1a',
                    border: '1px solid rgba(0,212,255,0.3)',
                    borderRadius: '6px',
                    fontSize: '11px',
                    fontFamily: 'JetBrains Mono',
                    color: '#e2e8f0',
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="space-y-1 mt-1">
              {domainStats.map((d, i) => (
                <div key={d.name} className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <div className="w-2 h-2 rounded-full" style={{ background: domainColors[i] }} />
                    <span className="text-text-secondary text-xs font-mono truncate">{d.name}</span>
                  </div>
                  <span className="text-text-muted text-xs font-mono">{d.value}%</span>
                </div>
              ))}
            </div>
          </GlowCard>

          {/* Exportar */}
          <GlowCard color="green" className="p-4">
            <h3 className="text-text-secondary text-xs font-mono font-semibold mb-3 uppercase tracking-widest">
              EXPORTAR
            </h3>
            <div className="space-y-2">
              <NeonButton
                variant="ghost"
                size="sm"
                fullWidth
                loading={isExporting}
                icon={<Download size={12} />}
                onClick={() => handleExport('json')}
              >
                Exportar JSON
              </NeonButton>
              <NeonButton
                variant="ghost"
                size="sm"
                fullWidth
                loading={isExporting}
                icon={<Download size={12} />}
                onClick={() => handleExport('csv')}
              >
                Exportar CSV
              </NeonButton>
            </div>
          </GlowCard>
        </div>

        {/* Grid de resultados */}
        <div className="xl:col-span-3">
          {isLoading ? (
            <PageLoader label="Buscando dados..." />
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              {displayItems.map((item) => (
                <ResultCard
                  key={item.id}
                  item={item}
                  query={debouncedQuery}
                  onClick={() => setSelectedItem(item)}
                />
              ))}
            </div>
          )}

          {/* Paginação simples */}
          {total > 12 && (
            <div className="flex items-center justify-center gap-3 mt-4">
              <NeonButton
                variant="ghost"
                size="sm"
                disabled={page === 1}
                onClick={() => setPage(p => Math.max(1, p - 1))}
              >
                ← Anterior
              </NeonButton>
              <span className="text-text-muted font-mono text-xs">Página {page}</span>
              <NeonButton
                variant="ghost"
                size="sm"
                onClick={() => setPage(p => p + 1)}
              >
                Próxima →
              </NeonButton>
            </div>
          )}
        </div>
      </div>

      {/* Modal de detalhe */}
      <AnimatePresence>
        {selectedItem && (
          <ItemDetailModal
            item={selectedItem}
            query={debouncedQuery}
            onClose={() => setSelectedItem(null)}
          />
        )}
      </AnimatePresence>
    </div>
  )
}
