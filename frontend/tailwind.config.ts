import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/features/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#080c14",
        surface: "#0d1320",
        "surface-elevated": "#131b2e",
        border: "#1e293b",
        foreground: "#f1f5f9",
        muted: "#94a3b8",
        accent: {
          DEFAULT: "#6366f1",
          hover: "#4f46e5",
          subtle: "rgba(99, 102, 241, 0.12)",
        },
        status: {
          healthy: "#10b981",
          warning: "#f59e0b",
          critical: "#ef4444",
          info: "#3b82f6",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
