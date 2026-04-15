import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "hsl(var(--bg) / <alpha-value>)",
        fg: "hsl(var(--fg) / <alpha-value>)",
        muted: "hsl(var(--muted) / <alpha-value>)",
        "muted-fg": "hsl(var(--muted-fg) / <alpha-value>)",
        border: "hsl(var(--border) / <alpha-value>)",
        "border-strong": "hsl(var(--border-strong) / <alpha-value>)",
        "surface-1": "hsl(var(--surface-1) / <alpha-value>)",
        "surface-2": "hsl(var(--surface-2) / <alpha-value>)",
        accent: "hsl(var(--accent) / <alpha-value>)",
        "accent-fg": "hsl(var(--accent-fg) / <alpha-value>)",
        buy: "hsl(var(--buy) / <alpha-value>)",
        sell: "hsl(var(--sell) / <alpha-value>)",
        warn: "hsl(var(--warn) / <alpha-value>)",
        info: "hsl(var(--info) / <alpha-value>)",
        ring: "hsl(var(--ring) / <alpha-value>)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: {
        card: "0 1px 0 0 hsl(0 0% 0% / 0.35), 0 0 0 1px hsl(var(--border))",
        elevated: "0 8px 24px -8px hsl(0 0% 0% / 0.6), 0 0 0 1px hsl(var(--border))",
        "ring-accent": "0 0 0 2px hsl(var(--bg)), 0 0 0 4px hsl(var(--ring))",
      },
      borderRadius: {
        card: "0.5rem",
        control: "0.375rem",
      },
      transitionDuration: {
        fast: "120ms",
      },
    },
  },
  plugins: [],
};

export default config;
