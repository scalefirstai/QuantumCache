import type { SkillSignatureRow } from "@/types/skill";

export function SkillSignature({ rows }: { rows: SkillSignatureRow[] }) {
  return (
    <section
      data-testid="skill-signature"
      className="bg-white border border-bny-mist rounded-lg px-4 py-3.5 mb-3.5"
    >
      <dl
        className="grid gap-y-2 gap-x-4 text-xs"
        style={{ gridTemplateColumns: "auto 1fr" }}
      >
        {rows.map((r) => (
          <SignatureRow key={r.label} row={r} />
        ))}
      </dl>
    </section>
  );
}

function SignatureRow({ row }: { row: SkillSignatureRow }) {
  return (
    <>
      <dt className="text-bny-fog">{row.label}</dt>
      <dd
        className={[
          "text-bny-ink m-0",
          row.mono ? "font-mono" : "",
        ].join(" ")}
      >
        {row.value}
      </dd>
    </>
  );
}
