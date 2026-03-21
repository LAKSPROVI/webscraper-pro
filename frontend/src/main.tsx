import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import App from './App.tsx'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30 * 1000,
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
      <Toaster
        position="bottom-right"
        toastOptions={{
          style: {
            background: '#0a0e1a',
            color: '#e2e8f0',
            border: '1px solid rgba(0,212,255,0.3)',
            borderRadius: '8px',
            fontFamily: '"Inter", sans-serif',
            fontSize: '14px',
          },
          success: {
            iconTheme: {
              primary: '#00ff88',
              secondary: '#0a0e1a',
            },
          },
          error: {
            iconTheme: {
              primary: '#ff3366',
              secondary: '#0a0e1a',
            },
          },
        }}
      />
    </QueryClientProvider>
  </React.StrictMode>,
)
