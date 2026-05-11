export function ReviewSummary({ summary }: { summary: string }) {
  return (
    <section
      data-testid="review-summary"
      className="bg-white border border-bny-mist rounded-lg px-4 py-4 mb-3.5"
    >
      <div className="text-[11px] text-bny-fog tracking-wider mb-1.5">
        REVIEW SUMMARY
      </div>
      <p className="text-[13px] text-bny-ink leading-[1.65] m-0">{summary}</p>
    </section>
  );
}
