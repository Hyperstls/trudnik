/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './djadmin/core/templates/**/*.html',
    './static/js/**/*.js'
  ],
  theme: {
    extend: {
      colors: {
        white: 'var(--ui-white)',
        neutral: {
          50: 'var(--ui-neutral-50)',
          100: 'var(--ui-neutral-100)',
          200: 'var(--ui-neutral-200)',
          300: 'var(--ui-neutral-300)',
          400: 'var(--ui-neutral-400)',
          500: 'var(--ui-neutral-500)',
          600: 'var(--ui-neutral-600)',
          700: 'var(--ui-neutral-700)',
          800: 'var(--ui-neutral-800)',
          900: 'var(--ui-neutral-900)'
        },
        primary: {
          50: 'var(--ui-primary-50)',
          100: 'var(--ui-primary-100)',
          200: 'var(--ui-primary-200)',
          300: 'var(--ui-primary-300)',
          400: 'var(--ui-primary-400)',
          500: 'var(--ui-primary-500)',
          600: 'var(--ui-primary-600)',
          700: 'var(--ui-primary-700)'
        },
        success: {
          light: '#d1fae5',
          DEFAULT: '#10b981',
          dark: '#047857'
        },
        warning: {
          light: '#fef3c7',
          DEFAULT: '#f59e0b',
          dark: '#d97706'
        },
        danger: {
          light: '#fee2e2',
          DEFAULT: '#ef4444',
          dark: '#dc2626'
        },
        info: {
          light: '#dbeafe',
          DEFAULT: '#3b82f6',
          dark: '#2563eb'
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 3px rgb(0 0 0 / 0.06), 0 1px 2px rgb(0 0 0 / 0.04)',
        elevated: '0 4px 12px rgb(0 0 0 / 0.08)',
      },
      borderRadius: {
        card: '0.875rem',
      },
      transitionDuration: {
        250: '250ms',
      },
    }
  }
}
