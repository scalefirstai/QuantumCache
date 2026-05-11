import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "media",
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Anthropic Sans",
          "-apple-system",
          "system-ui",
          "Segoe UI",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
      colors: {
        bny: {
          ink: "#04243C",
          slate: "#4A6478",
          fog: "#7B8E9D",
          mist: "#BFD9E4",
          haze: "#E1ECF1",
          sky: "#7FCAD5",
          teal: "#2B9CAE",
          tealLight: "#DDF1F4",
          paper: "#F4F8FA",
          ochre: "#BA7517",
          danger: "#A32D2D",
          ok: "#3B6D11",
        },
        lane: {
          knowledgeBg: "#E1F5EE",
          knowledgeFg: "#085041",
          canonicalBg: "#EEEDFE",
          canonicalFg: "#3C3489",
          auditBg: "#F1EFE8",
          auditFg: "#444441",
        },
      },
      borderRadius: {
        sm: "4px",
        md: "6px",
        lg: "10px",
      },
    },
  },
} satisfies Config;
