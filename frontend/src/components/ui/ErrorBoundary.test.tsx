import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ErrorBoundary from './ErrorBoundary'

function BrokenComponent(): JSX.Element {
  throw new Error('Erro simulado')
}

describe('ErrorBoundary', () => {
  it('exibe fallback quando um componente interno falha', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => undefined)

    render(
      <ErrorBoundary>
        <BrokenComponent />
      </ErrorBoundary>
    )

    expect(screen.getByText(/Falha inesperada no dashboard/i)).toBeInTheDocument()
    spy.mockRestore()
  })
})
