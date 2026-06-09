/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          purple: '#4B00AA',
          'purple-light': '#7855FA',
          teal: '#1FDDE9',
          green: '#92DD23',
          coral: '#FF9178',
          dark: '#131313',
          'dark-blue': '#0092B0',
          'deep-purple': '#391699',
        },
      },
      fontFamily: {
        sans: ['Arial', 'Helvetica', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
