import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

const config: Config = {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      padding: "1.5rem",
      screens: {
        "2xl": "1440px",
      },
    },
    extend: {
      colors: {
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        panel: "hsl(var(--panel))",
        card: "hsl(var(--card))",
        muted: "hsl(var(--muted))",
        "muted-foreground": "hsl(var(--muted-foreground))",
        accent: "hsl(var(--accent))",
        "accent-foreground": "hsl(var(--accent-foreground))",
        border: "hsl(var(--border))",
        ring: "hsl(var(--ring))",
        "surface-soft": "hsl(var(--surface-soft) / <alpha-value>)",
        "surface-subtle": "hsl(var(--surface-subtle) / <alpha-value>)",
        "surface-strong": "hsl(var(--surface-strong) / <alpha-value>)",
        "surface-selected": "hsl(var(--surface-selected) / <alpha-value>)",
        "surface-selected-strong": "hsl(var(--surface-selected-strong) / <alpha-value>)",
        "surface-contrast": "hsl(var(--surface-contrast) / <alpha-value>)",
        "border-soft": "hsl(var(--border-soft) / <alpha-value>)",
        "border-strong": "hsl(var(--border-strong) / <alpha-value>)",
        success: "hsl(var(--success-bg) / <alpha-value>)",
        "success-foreground": "hsl(var(--success-fg) / <alpha-value>)",
        warning: "hsl(var(--warning-bg) / <alpha-value>)",
        "warning-foreground": "hsl(var(--warning-fg) / <alpha-value>)",
        danger: "hsl(var(--danger-bg) / <alpha-value>)",
        "danger-foreground": "hsl(var(--danger-fg) / <alpha-value>)",
        info: "hsl(var(--info-bg) / <alpha-value>)",
        "info-foreground": "hsl(var(--info-fg) / <alpha-value>)",
      },
      borderRadius: {
        xl: "1rem",
        "2xl": "1.5rem",
      },
      boxShadow: {
        panel: "var(--shadow-panel)",
        card: "var(--shadow-card)",
      },
      gridTemplateColumns: {
        import: "minmax(220px, 1.15fr) minmax(320px, 1.55fr) minmax(260px, 1fr)",
      },
      transitionTimingFunction: {
        apple: "cubic-bezier(0.22, 1, 0.36, 1)",
      },
      keyframes: {
        "fade-in-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-in-up": "fade-in-up 0.22s cubic-bezier(0.22, 1, 0.36, 1) both",
      },
    },
  },
  plugins: [animate],
};

export default config;
