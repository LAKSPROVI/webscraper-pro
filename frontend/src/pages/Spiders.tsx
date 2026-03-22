import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Bug, Play, Edit2, Trash2, Copy, Power, Clock, Activity,
  Plus, X, CheckCircle, AlertCircle, ShieldCheck, ShieldOff, RefreshCcw, HeartPulse
} from 'lucide-react'
import { format } from 'date-fns'
import { ptBR } from 'date-fns/locale'
import clsx from 'clsx'
import {
  useSpiders,
  useCreateSpider,
  useUpdateSpider,
  useDeleteSpider,
  useProxySettings,
  useEnableProxy,
  useDisableProxy,
  useRefreshProxyPool,
  useProxyHealthCheck,
} from '../hooks/useApi'
import type { SpiderConfig } from '../hooks/useApi'
import GlowCard from '../components/ui/GlowCard'
import NeonButton from '../components/ui/NeonButton'
import { PageLoader } from '../components/ui/LoadingSpinner'
import { useScrape } from '../hooks/useApi'

const DEFAULT_YAML = `# Configuração do Spider
name: meu-spider
type: generic
settings:
  follow_links: true
  max_depth: 2
  delay: 1.0
  timeout: 30
  user_agent: "WebScraper/2.0"
  
selectors:
  title: "h1, h2.title"
  content: "article, .content, main p"
  links: "a[href]"
  
filters:
  exclude_urls:
    - "*.pdf"
    - "/login"
    - "/register"
  
output:
  format: json
  include_metadata: true
`

// Mock spiders
const mockSpiders: SpiderConfig[] = [
  {
    id: 'sp-001',
    name: 'Spider Genérico v2',
    type: 'generic',
    description: 'Extração genérica de conteúdo web com suporte a paginação',
    is_active: true,
    config_yaml: DEFAULT_YAML,
    last_used: new Date(Date.now() - 3600000).toISOString(),
    total_runs: 847,
    created_at: new Date(Date.now() - 30 * 24 * 3600000).toISOString(),
  },
  {
    id: 'sp-002',
    name: 'Spider de Notícias',
    type: 'news',
    description: 'Coleta artigos e notícias com extração de metadados',
    is_active: true,
    config_yaml: DEFAULT_YAML,
    last_used: new Date(Date.now() - 7200000).toISOString(),
    total_runs: 1204,
    created_at: new Date(Date.now() - 60 * 24 * 3600000).toISOString(),
  },
  {
    id: 'sp-003',
    name: 'Spider E-commerce',
    type: 'ecommerce',
    description: 'Extração de produtos, preços e avaliações',
    is_active: false,
    config_yaml: DEFAULT_YAML,
    last_used: new Date(Date.now() - 86400000).toISOString(),
    total_runs: 345,
    created_at: new Date(Date.now() - 45 * 24 * 3600000).toISOString(),
  },
  {
    id: 'sp-004',
    name: 'Spider de Artigos',
    type: 'article',
    description: 'Coleta artigos longos com suporte a conteúdo dinâmico',
    is_active: true,
    config_yaml: DEFAULT_YAML,
    last_used: new Date(Date.now() - 1800000).toISOString(),
    total_runs: 562,
    created_at: new Date(Date.now() - 15 * 24 * 3600000).toISOString(),
  },
]

const typeColors: Record<string, { text: string; bg: string; border: string }> = {
  generic: { text: 'text-neon-cyan', bg: 'bg-neon-cyan-dim', border: 'border-neon-cyan-dim' },
  news: { text: 'text-neon-purple', bg: 'bg-neon-purple-dim', border: 'border-neon-purple-dim' },
  article: { text: 'text-neon-green', bg: 'bg-neon-green-dim', border: 'border-neon-green-dim' },
  ecommerce: { text: 'text-neon-amber', bg: 'bg-neon-amber-dim', border: 'border-neon-amber-dim' },
}

// Modal Editor YAML
function YamlEditorModal({
  spider,
  onClose,
  onSave,
}: {
  spider: SpiderConfig | null
  onClose: () => void
  onSave: (config: Partial<SpiderConfig>) => void
}) {
  const [yaml, setYaml] = useState(spider?.config_yaml || DEFAULT_YAML)
  const [name, setName] = useState(spider?.name || '')
  const [description, setDescription] = useState(spider?.description || '')
  const [type, setType] = useState(spider?.type || 'generic')
  const [isValidating, setIsValidating] = useState(false)
  const [validationResult, setValidationResult] = useState<'valid' | 'invalid' | null>(null)

  const handleValidate = async () => {
    setIsValidating(true)
    await new Promise(r => setTimeout(r, 800))
    setIsValidating(false)
    // Validação simples: verifica se tem "name:" e "type:"
    const isValid = yaml.includes('name:') && yaml.includes('type:')
    setValidationResult(isValid ? 'valid' : 'invalid')
  }

  const handleSave = () => {
    onSave({ name, description, type, config_yaml: yaml })
    onClose()
  }

  return (
    <div className="fixed inset-0 z-modal flex items-center justify-center modal-overlay" onClick={onClose}>
      <motion.div
        className="w-full max-w-2xl mx-4"
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.9 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="glass-card border border-neon-cyan-mid rounded-xl overflow-hidden max-h-[90vh] flex flex-col">
          {/* Header */}
          <div className="p-4 border-b border-border-dim flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Bug size={16} className="text-neon-cyan" />
              <h3 className="text-text-primary font-semibold">
                {spider ? 'Editar Spider' : 'Nova Configuração'}
              </h3>
            </div>
            <button onClick={onClose} className="text-text-muted hover:text-text-primary">
              <X size={16} />
            </button>
          </div>

          {/* Form */}
          <div className="flex-1 overflow-y-auto p-5 space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-text-muted text-xs font-mono block mb-1.5">NOME</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="nome-do-spider"
                  className="input-neon w-full px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="text-text-muted text-xs font-mono block mb-1.5">TIPO</label>
                <select
                  value={type}
                  onChange={(e) => setType(e.target.value)}
                  className="select-neon w-full px-3 py-2 text-sm"
                >
                  <option value="generic">Genérico</option>
                  <option value="news">Notícias</option>
                  <option value="article">Artigo</option>
                  <option value="ecommerce">E-commerce</option>
                </select>
              </div>
            </div>

            <div>
              <label className="text-text-muted text-xs font-mono block mb-1.5">DESCRIÇÃO</label>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Descrição do spider..."
                className="input-neon w-full px-3 py-2 text-sm"
              />
            </div>

            {/* Editor YAML */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-text-muted text-xs font-mono">CONFIGURAÇÃO YAML</label>
                <div className="flex items-center gap-2">
                  {validationResult === 'valid' && (
                    <span className="text-neon-green text-xs font-mono flex items-center gap-1">
                      <CheckCircle size={11} /> Válido
                    </span>
                  )}
                  {validationResult === 'invalid' && (
                    <span className="text-neon-red text-xs font-mono flex items-center gap-1">
                      <AlertCircle size={11} /> Inválido
                    </span>
                  )}
                  <NeonButton
                    variant="ghost"
                    size="sm"
                    loading={isValidating}
                    onClick={handleValidate}
                  >
                    Validar YAML
                  </NeonButton>
                </div>
              </div>
              <textarea
                value={yaml}
                onChange={(e) => setYaml(e.target.value)}
                className={clsx(
                  'w-full h-56 px-4 py-3 rounded-lg text-xs font-mono',
                  'bg-bg-base border resize-y',
                  'text-neon-green leading-relaxed',
                  'focus:outline-none focus:border-neon-cyan-mid',
                  validationResult === 'invalid' ? 'border-neon-red' : 'border-border-mid',
                  'placeholder:text-text-muted'
                )}
                spellCheck={false}
              />
            </div>
          </div>

          {/* Footer */}
          <div className="p-4 border-t border-border-dim flex gap-3">
            <NeonButton variant="ghost" onClick={onClose} className="flex-1">Cancelar</NeonButton>
            <NeonButton variant="primary" onClick={handleSave} className="flex-1">
              {spider ? 'Salvar Alterações' : 'Criar Spider'}
            </NeonButton>
          </div>
        </div>
      </motion.div>
    </div>
  )
}

// Card de Spider
function SpiderCard({ spider }: { spider: SpiderConfig }) {
  const colors = typeColors[spider.type] || typeColors.generic
  const { mutate: update } = useUpdateSpider()
  const { mutate: del } = useDeleteSpider()
  const { mutate: createSpider } = useCreateSpider()
  const { mutate: scrape } = useScrape()
  const [showEditor, setShowEditor] = useState(false)

  const toggleActive = () => {
    update({ id: spider.id, is_active: !spider.is_active })
  }

  return (
    <>
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className={clsx(
          'glass-card border p-5 transition-all duration-200',
          spider.is_active
            ? 'border-neon-cyan-dim hover:border-neon-cyan-mid hover:shadow-glow-cyan'
            : 'border-border-dim hover:border-border-mid opacity-60'
        )}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex items-center gap-3">
            <div className={clsx('p-2 rounded-lg', colors.bg)}>
              <Bug size={18} className={clsx(colors.text, spider.is_active && 'spider-float')} />
            </div>
            <div>
              <h3 className="text-text-primary font-semibold text-sm">{spider.name}</h3>
              <span className={clsx('text-xs font-mono px-2 py-0.5 rounded-full border', colors.text, colors.bg, colors.border)}>
                {spider.type}
              </span>
            </div>
          </div>
          {/* Toggle ativo */}
          <button
            onClick={toggleActive}
            className={clsx(
              'flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-mono border transition-all',
              spider.is_active
                ? 'text-neon-green bg-neon-green-dim border-neon-green-dim'
                : 'text-text-muted bg-bg-card border-border-dim'
            )}
          >
            <Power size={10} />
            {spider.is_active ? 'Ativo' : 'Inativo'}
          </button>
        </div>

        {/* Descrição */}
        {spider.description && (
          <p className="text-text-secondary text-xs mb-3 leading-relaxed">{spider.description}</p>
        )}

        {/* Stats */}
        <div className="grid grid-cols-2 gap-2 mb-4">
          <div className="bg-bg-surface rounded-lg p-2">
            <p className="text-text-muted text-xs font-mono">Execuções</p>
            <p className={clsx('font-mono font-bold text-sm', colors.text)}>{spider.total_runs.toLocaleString('pt-BR')}</p>
          </div>
          <div className="bg-bg-surface rounded-lg p-2">
            <p className="text-text-muted text-xs font-mono">Último uso</p>
            <p className="text-text-secondary text-xs font-mono">
              {spider.last_used
                ? format(new Date(spider.last_used), 'dd/MM HH:mm', { locale: ptBR })
                : 'Nunca'}
            </p>
          </div>
        </div>

        {/* Ações */}
        <div className="flex gap-2">
          <NeonButton variant="ghost" size="sm" icon={<Play size={11} />} className="flex-1"
            onClick={() => scrape({ url: 'https://example.com', spider_type: spider.type })}>
            Executar
          </NeonButton>
          <button
            onClick={() => setShowEditor(true)}
            className="p-1.5 rounded-lg border border-border-dim text-text-muted hover:border-neon-cyan-mid hover:text-neon-cyan transition-all"
            title="Editar"
          >
            <Edit2 size={13} />
          </button>
          <button
            onClick={() => createSpider({
              name: `${spider.name}-copy-${Date.now().toString().slice(-4)}`,
              type: spider.type,
              description: spider.description,
              is_active: spider.is_active,
              config_yaml: spider.config_yaml,
              last_used: undefined,
            })}
            className="p-1.5 rounded-lg border border-border-dim text-text-muted hover:border-neon-purple-mid hover:text-purple-300 transition-all"
            title="Duplicar"
          >
            <Copy size={13} />
          </button>
          <button
            onClick={() => del(spider.id)}
            className="p-1.5 rounded-lg border border-border-dim text-text-muted hover:border-neon-red-dim hover:text-neon-red transition-all"
            title="Deletar"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </motion.div>

      <AnimatePresence>
        {showEditor && (
          <YamlEditorModal
            spider={spider}
            onClose={() => setShowEditor(false)}
            onSave={(config) => update({ id: spider.id, ...config })}
          />
        )}
      </AnimatePresence>
    </>
  )
}

export default function Spiders() {
  const { data, isLoading } = useSpiders()
  const { data: proxySettings, refetch: refetchProxy } = useProxySettings()
  const { mutate: enableProxy, isPending: enablingProxy } = useEnableProxy()
  const { mutate: disableProxy, isPending: disablingProxy } = useDisableProxy()
  const { mutate: refreshPool, isPending: refreshingPool } = useRefreshProxyPool()
  const { mutate: healthCheck, isPending: healthChecking } = useProxyHealthCheck()
  const [showNewModal, setShowNewModal] = useState(false)
  const { mutate: create } = useCreateSpider()

  const displaySpiders = data || mockSpiders

  return (
    <div className="space-y-4 animate-fade-in">
      <GlowCard color="purple" className="p-4">
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-text-primary font-semibold text-sm">Controle de Proxy</p>
              <p className="text-text-muted text-xs font-mono">
                Status global: {proxySettings?.enabled ? 'ATIVO' : 'INATIVO'} | Pool ativo: {proxySettings?.pool.active_proxies.size ?? 0} | Pool legado: {proxySettings?.pool.proxies_pool.size ?? 0}
              </p>
            </div>
            <div className={clsx(
              'px-2 py-1 rounded-lg text-xs font-mono border',
              proxySettings?.enabled
                ? 'text-neon-green border-neon-green-dim bg-neon-green-dim'
                : 'text-text-muted border-border-dim bg-bg-surface'
            )}>
              {proxySettings?.enabled ? 'PROXY ON' : 'PROXY OFF'}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <NeonButton
              size="sm"
              variant="primary"
              icon={<ShieldCheck size={12} />}
              loading={enablingProxy}
              onClick={() => enableProxy()}
            >
              Ativar Proxy
            </NeonButton>
            <NeonButton
              size="sm"
              variant="ghost"
              icon={<ShieldOff size={12} />}
              loading={disablingProxy}
              onClick={() => disableProxy()}
            >
              Desativar Proxy
            </NeonButton>
            <NeonButton
              size="sm"
              variant="ghost"
              icon={<RefreshCcw size={12} />}
              loading={refreshingPool}
              onClick={() => refreshPool()}
            >
              Atualizar Pool
            </NeonButton>
            <NeonButton
              size="sm"
              variant="ghost"
              icon={<HeartPulse size={12} />}
              loading={healthChecking}
              onClick={() => healthCheck()}
            >
              Health Check
            </NeonButton>
            <NeonButton
              size="sm"
              variant="ghost"
              onClick={() => refetchProxy()}
            >
              Recarregar Status
            </NeonButton>
          </div>
        </div>
      </GlowCard>

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-text-muted text-sm">
            <span className="text-neon-cyan font-mono font-bold">{displaySpiders.length}</span> spiders configurados
          </p>
        </div>
        <NeonButton
          icon={<Plus size={14} />}
          onClick={() => setShowNewModal(true)}
        >
          Nova Config
        </NeonButton>
      </div>

      {/* Grid de Spiders */}
      {isLoading ? (
        <PageLoader label="Carregando spiders..." />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {displaySpiders.map((spider) => (
            <SpiderCard key={spider.id} spider={spider} />
          ))}
        </div>
      )}

      {/* Modal Nova Config */}
      <AnimatePresence>
        {showNewModal && (
          <YamlEditorModal
            spider={null}
            onClose={() => setShowNewModal(false)}
            onSave={(config) => create({
              name: config.name || 'Novo Spider',
              type: config.type || 'generic',
              description: config.description,
              is_active: true,
              config_yaml: config.config_yaml || DEFAULT_YAML,
              last_used: undefined,
            })}
          />
        )}
      </AnimatePresence>
    </div>
  )
}
