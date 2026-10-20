/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    borderRadius: {
      none: '0',
      sm:   '0',
      DEFAULT: '0',
      md:   '0',
      lg:   '0',
      xl:   '0',
      '2xl': '0',
      '3xl': '0',
      full: '9999px',   // keep for pill / avatar shapes if ever needed
    },
    extend: {
      colors: {
        surface: 'var(--color-surface)',
        card:    'var(--color-card)',
        border:  'var(--color-border)',
        // Override the slate palette so every slate utility reads a CSS
        // variable.  In dark themes the variables match Tailwind defaults;
        // in light mode they are flipped to produce readable light-mode UI.
        slate: {
          50:  'var(--sl-50)',
          100: 'var(--sl-100)',
          200: 'var(--sl-200)',
          300: 'var(--sl-300)',
          400: 'var(--sl-400)',
          500: 'var(--sl-500)',
          600: 'var(--sl-600)',
          700: 'var(--sl-700)',
          800: 'var(--sl-800)',
          900: 'var(--sl-900)',
          950: 'var(--sl-950)',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
}
