/** LifeFlow design tokens. Semantic colours resolve to CSS variables defined in
 *  input.css, so light/dark themes switch without duplicating utility classes. */
const path = require("path");
const rgb = (v) => `rgb(var(${v}) / <alpha-value>)`;

module.exports = {
  darkMode: "class",
  content: [
    path.join(__dirname, "../templates/**/*.html"),
    path.join(__dirname, "../apps/**/templates/**/*.html"),
    path.join(__dirname, "../static/js/**/*.js"),
    path.join(__dirname, "../apps/**/*.py"),
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Inter Variable"', '"Noto Sans Arabic Variable"', "Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
      },
      colors: {
        canvas: rgb("--c-canvas"),
        surface: rgb("--c-surface"),
        subtle: rgb("--c-subtle"),
        line: rgb("--c-line"),
        ink: rgb("--c-ink"),
        muted: rgb("--c-muted"),
        faint: rgb("--c-faint"),
        brand: {
          DEFAULT: rgb("--c-brand"),
          strong: rgb("--c-brand-strong"),
          soft: rgb("--c-brand-soft"),
        },
        tone: { DEFAULT: rgb("--tone"), strong: rgb("--tone-strong") },
        success: rgb("--c-success"),
        warning: rgb("--c-warning"),
        danger: rgb("--c-danger"),
      },
      borderRadius: { xl: "0.875rem", "2xl": "1.125rem" },
      boxShadow: {
        card: "0 1px 2px rgb(15 23 42 / 0.04), 0 1px 3px rgb(15 23 42 / 0.04)",
        pop: "0 10px 30px -10px rgb(15 23 42 / 0.25), 0 4px 10px -4px rgb(15 23 42 / 0.1)",
      },
      keyframes: {
        shimmer: { "100%": { transform: "translateX(100%)" } },
        "fade-in": { from: { opacity: 0, transform: "translateY(4px)" }, to: { opacity: 1, transform: "none" } },
      },
      animation: {
        "fade-in": "fade-in .18s ease-out both",
      },
    },
  },
  plugins: [require("@tailwindcss/forms")({ strategy: "class" })],
};
