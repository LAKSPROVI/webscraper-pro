import React from 'react'

type ErrorBoundaryProps = {
  children: React.ReactNode
}

type ErrorBoundaryState = {
  hasError: boolean
  message: string
}

export default class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, message: '' }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return {
      hasError: true,
      message: error.message || 'Erro inesperado na interface.',
    }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    console.error('Frontend ErrorBoundary capturou erro:', error, errorInfo)
  }

  handleReload = () => {
    window.location.reload()
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center px-6" style={{ backgroundColor: '#050810' }}>
          <div className="glass-card max-w-lg w-full p-8 border border-red-500/40">
            <h1 className="text-2xl font-bold text-red-300">Falha inesperada no dashboard</h1>
            <p className="mt-3 text-text-muted">
              Ocorreu um erro no frontend. A melhor ação agora é recarregar a página.
            </p>
            <p className="mt-3 text-xs text-red-200/80 font-mono break-all">{this.state.message}</p>

            <button
              className="mt-6 px-4 py-2 rounded-md border border-neon-cyan-mid text-neon-cyan hover:bg-neon-cyan/10 transition"
              onClick={this.handleReload}
            >
              Recarregar
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
