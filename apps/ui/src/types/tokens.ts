// Structured rich-text replacement for ad-hoc HTML in fixtures.
// All copy that needs inline emphasis or code is expressed as a Token[].
// The renderer in components/shell/Tokens.tsx is the only consumer.

export type Token =
  | { kind: "text"; value: string }
  | { kind: "strong"; value: string }
  | { kind: "code"; value: string }
  | { kind: "em"; value: string };

export type RichText = Token[];
