/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/templates/**/*.html",
    "./app/static/**/*.css",
  ],
  theme: {
    extend: {
      fontFamily: {
        'display': ['Playfair Display', 'serif'],
        'body': ['Lato', 'sans-serif'],
      },
      colors: {
        'safari-green': {
          DEFAULT: '#2E5239',
          dark: '#1e3d2a',
          light: '#f0f7f3',
        },
        'safari-amber': {
          600: '#d97706',
          700: '#b45309',
        },
        'safari-cream': '#FAF9F6',
        'safari-dark': '#0f172a',
      },
    },
  },
  plugins: [],
}

