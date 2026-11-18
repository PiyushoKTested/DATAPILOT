/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        navy: {
          950: '#070C18',
          900: '#0B1224',
          850: '#0E172B',
          800: '#121D36',
          700: '#1A2744',
          600: '#243354',
        },
        accent: {
          DEFAULT: '#3B82F6',
          soft: '#60A5FA',
          violet: '#8B5CF6',
          cyan: '#06B6D4',
        },
      },
      fontFamily: {
        sans: [
          'Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI',
          'Roboto', 'Helvetica', 'Arial', 'sans-serif',
        ],
        mono: ['JetBrains Mono', 'Consolas', 'Monaco', 'monospace'],
      },
      boxShadow: {
        card: '0 1px 2px 0 rgba(0,0,0,.28), 0 8px 24px -8px rgba(0,0,0,.45)',
        glow: '0 0 0 1px rgba(59,130,246,.28), 0 12px 40px -12px rgba(59,130,246,.42)',
      },
      keyframes: {
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
      },
      animation: {
        'fade-up': 'fade-up .38s cubic-bezier(.22,1,.36,1) both',
        'fade-in': 'fade-in .28s ease-out both',
      },
    },
  },
  plugins: [],
}
