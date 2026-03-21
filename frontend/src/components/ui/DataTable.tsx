import React from 'react'
import clsx from 'clsx'

interface Column<T> {
  key: string
  header: string
  width?: string
  align?: 'left' | 'center' | 'right'
  render?: (value: unknown, row: T) => React.ReactNode
  sortable?: boolean
}

interface DataTableProps<T> {
  data: T[]
  columns: Column<T>[]
  onRowClick?: (row: T) => void
  getRowKey?: (row: T, index: number) => string
  emptyMessage?: string
  loading?: boolean
  striped?: boolean
  className?: string
  isRowRunning?: (row: T) => boolean
}

function getNestedValue(obj: unknown, key: string): unknown {
  return key.split('.').reduce((acc: unknown, part) => {
    if (acc && typeof acc === 'object') {
      return (acc as Record<string, unknown>)[part]
    }
    return undefined
  }, obj)
}

export default function DataTable<T>({
  data,
  columns,
  onRowClick,
  getRowKey,
  emptyMessage = 'Nenhum dado encontrado',
  loading = false,
  striped = true,
  className,
  isRowRunning,
}: DataTableProps<T>) {
  if (loading) {
    return (
      <div className={clsx('w-full overflow-hidden rounded-xl border border-border-dim', className)}>
        <div className="min-w-full">
          <div className="bg-bg-card px-4 py-3 border-b border-border-dim flex gap-4">
            {columns.map((col) => (
              <div key={col.key} className="h-4 bg-bg-surface rounded animate-pulse flex-1" />
            ))}
          </div>
          {[...Array(5)].map((_, i) => (
            <div key={i} className="px-4 py-3 border-b border-border-dim flex gap-4">
              {columns.map((col) => (
                <div key={col.key} className="h-4 bg-bg-card rounded animate-pulse flex-1" />
              ))}
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className={clsx('w-full overflow-x-auto rounded-xl border border-border-dim', className)}>
      <table className="min-w-full">
        {/* Header */}
        <thead>
          <tr className="bg-bg-card border-b border-border-mid">
            {columns.map((col) => (
              <th
                key={col.key}
                className={clsx(
                  'px-4 py-3 text-xs font-semibold text-text-muted uppercase tracking-widest',
                  'font-mono whitespace-nowrap',
                  col.align === 'center' && 'text-center',
                  col.align === 'right' && 'text-right',
                  !col.align && 'text-left',
                  col.width
                )}
                style={col.width ? { width: col.width } : undefined}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        {/* Body */}
        <tbody>
          {data.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                className="px-4 py-12 text-center text-text-muted text-sm font-mono"
              >
                <div className="flex flex-col items-center gap-2">
                  <span className="text-2xl opacity-30">⚡</span>
                  <span>{emptyMessage}</span>
                </div>
              </td>
            </tr>
          ) : (
            data.map((row, rowIndex) => {
              const rowKey = getRowKey ? getRowKey(row, rowIndex) : String(rowIndex)
              const running = isRowRunning ? isRowRunning(row) : false

              return (
                <tr
                  key={rowKey}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={clsx(
                    'relative border-b border-border-dim transition-all duration-150',
                    'group',
                    striped && rowIndex % 2 === 0 ? 'bg-bg-card' : 'bg-bg-base',
                    onRowClick && 'cursor-pointer hover:bg-bg-card-hover',
                    running && 'row-running',
                    running && 'bg-neon-cyan-dim bg-opacity-5'
                  )}
                >
                  {columns.map((col) => {
                    const rawValue = getNestedValue(row, col.key)
                    return (
                      <td
                        key={col.key}
                        className={clsx(
                          'px-4 py-3 text-sm',
                          col.align === 'center' && 'text-center',
                          col.align === 'right' && 'text-right',
                          !col.align && 'text-left',
                          'group-hover:text-text-primary',
                        )}
                      >
                        {col.render ? col.render(rawValue, row) : (
                          <span className="text-text-secondary font-mono text-xs">
                            {rawValue !== undefined && rawValue !== null ? String(rawValue) : '—'}
                          </span>
                        )}
                      </td>
                    )
                  })}
                </tr>
              )
            })
          )}
        </tbody>
      </table>
    </div>
  )
}
