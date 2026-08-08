/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        zara: {
          bg: '#020604',
          bgGlass: '#08140e88',
          bgGlassStrong: '#0c1f14cc',
          surface: '#0a1810',
          surfaceHover: '#10281c',
          border: '#1a4d36',
          borderSoft: '#0d2b1f',
          borderGlow: '#62f6aa',
          green: '#62f6aa',
          greenBright: '#a7ffd0',
          greenDim: '#2ea86e',
          greenDeep: '#0d5c36',
          cyan: '#00ffff',
          cyanDim: '#00cccc',
          purple: '#a855f7',
          purpleGlow: '#c084fc',
          amber: '#f59e0b',
          red: '#ef4444',
          text: '#e7fff0',
          textDim: '#8fb8a0',
          textMuted: '#5a7d6a',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'monospace'],
        sans: ['Space Grotesk', 'sans-serif'],
        display: ['Orbitron', 'sans-serif'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow': 'glow 2s ease-in-out infinite alternate',
        'float': 'float 6s ease-in-out infinite',
        'spin-slow': 'spin 8s linear infinite',
      },
      keyframes: {
        glow: {
          '0%, 100%': { boxShadow: '0 0 20px #62f6aa44, 0 0 40px #62f6aa22' },
          '50%': { boxShadow: '0 0 40px #62f6aa88, 0 0 80px #62f6aa44' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-10px)' },
        },
      },
    },
  },
  plugins: [],
}
