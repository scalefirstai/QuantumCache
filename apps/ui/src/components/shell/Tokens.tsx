import type { RichText, Token } from "@/types/tokens";

function renderToken(t: Token, i: number) {
  switch (t.kind) {
    case "text":
      return <span key={i}>{t.value}</span>;
    case "strong":
      return (
        <strong key={i} className="font-medium">
          {t.value}
        </strong>
      );
    case "em":
      return <em key={i}>{t.value}</em>;
    case "code":
      return (
        <code
          key={i}
          className="font-mono text-[12px] px-1.5 py-px rounded bg-[var(--color-background-tertiary)] text-bny-ink"
        >
          {t.value}
        </code>
      );
  }
}

export function Tokens({ value }: { value: RichText }) {
  return <>{value.map((t, i) => renderToken(t, i))}</>;
}

/** Plain-text projection — for aria labels, screenshots, etc. */
export function tokensToText(value: RichText): string {
  return value.map((t) => t.value).join("");
}
