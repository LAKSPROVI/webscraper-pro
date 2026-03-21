/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        'neon-cyan': '#00d4ff',
        'neon-cyan-dim': 'rgba(0,212,255,0.2)',
        'neon-cyan-mid': 'rgba(0,212,255,0.5)',
        'neon-purple': '#7c3aed',
        'neon-purple-dim': 'rgba(124,58,237,0.2)',
        'neon-purple-mid': 'rgba(124,58,237,0.5)',
        'neon-green': '#00ff88',
        'neon-green-dim': 'rgba(0,255,136,0.2)',
        'neon-green-mid': 'rgba(0,255,136,0.5)',
        'neon-amber': '#ffb800',
        'neon-amber-dim': 'rgba(255,184,0,0.2)',
        'neon-red': '#ff3366',
        'neon-red-dim': 'rgba(255,51,102,0.2)',
        'bg-base': '#050810',
        'bg-card': '#0a0e1a',
        'bg-card-hover': '#0d1220',
        'bg-surface': '#111827',
        'border-dim': 'rgba(255,255,255,0.06)',
        'border-mid': 'rgba(255,255,255,0.12)',
        'text-primary': '#e2e8f0',
        'text-secondary': '#94a3b8',
        'text-muted': '#475569',
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        'glow-cyan': '0 0 20px rgba(0,212,255,0.3), 0 0 40px rgba(0,212,255,0.1)',
        'glow-cyan-sm': '0 0 10px rgba(0,212,255,0.4)',
        'glow-purple': '0 0 20px rgba(124,58,237,0.3), 0 0 40px rgba(124,58,237,0.1)',
        'glow-green': '0 0 20px rgba(0,255,136,0.3), 0 0 40px rgba(0,255,136,0.1)',
        'glow-amber': '0 0 20px rgba(255,184,0,0.3), 0 0 40px rgba(255,184,0,0.1)',
        'glow-red': '0 0 20px rgba(255,51,102,0.3)',
        'card': '0 4px 24px rgba(0,0,0,0.4), 0 1px 0 rgba(255,255,255,0.05)',
        'inner-cyan': 'inset 0 0 20px rgba(0,212,255,0.05)',
      },
      animation: {
        'pulse-glow': 'pulse-glow 2s ease-in-out infinite',
        'pulse-glow-fast': 'pulse-glow 1s ease-in-out infinite',
        'float': 'float 6s ease-in-out infinite',
        'scan-line': 'scan-line 3s linear infinite',
        'data-flow': 'data-flow 0.5s ease-out',
        'fade-in': 'fade-in 0.3s ease-out',
        'slide-up': 'slide-up 0.4s ease-out',
        'glow-border': 'glow-border 3s linear infinite',
        'shimmer': 'shimmer 2s linear infinite',
        'spin-slow': 'spin 3s linear infinite',
        'bounce-subtle': 'bounce-subtle 2s ease-in-out infinite',
      },
      keyframes: {
        'pulse-glow': {
          '0%, 100%': { opacity: '1', boxShadow: '0 0 10px rgba(0,212,255,0.5)' },
          '50%': { opacity: '0.7', boxShadow: '0 0 20px rgba(0,212,255,0.8), 0 0 30px rgba(0,212,255,0.4)' },
        },
        'float': {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-8px)' },
        },
        'scan-line': {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(100%)' },
        },
        'data-flow': {
          '0%': { opacity: '0', transform: 'translateY(-10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'slide-up': {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'glow-border': {
          '0%, 100%': { borderColor: 'rgba(0,212,255,0.3)' },
          '50%': { borderColor: 'rgba(0,212,255,0.8)' },
        },
        'shimmer': {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        'bounce-subtle': {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-3px)' },
        },
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(ellipse at center, var(--tw-gradient-stops))',
        'gradient-cyan': 'linear-gradient(135deg, #00d4ff 0%, #7c3aed 100%)',
        'gradient-green': 'linear-gradient(135deg, #00ff88 0%, #00d4ff 100%)',
        'shimmer-gradient': 'linear-gradient(90deg, transparent 0%, rgba(0,212,255,0.1) 50%, transparent 100%)',
      },
    },
  },
  plugins: [],
}
