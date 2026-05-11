import type { PerformanceReview } from "@/types/review";

export function ReviewHeader({ data }: { data: PerformanceReview }) {
  return (
    <header
      className="bg-bny-ink text-white px-5 py-4 rounded-t-lg grid items-center gap-3.5"
      style={{ gridTemplateColumns: "56px 1fr auto" }}
    >
      <div className="w-14 h-14 rounded-full bg-bny-teal flex items-center justify-center text-lg font-medium border-2 border-bny-sky">
        DE
      </div>
      <div>
        <div className="flex items-center gap-2.5">
          <div className="text-base font-medium">Aria · DDQ specialist</div>
          <span className="bg-bny-teal text-white text-[10px] px-2 py-0.5 rounded-full font-medium">
            PERFORMANCE REVIEW
          </span>
        </div>
        <div className="text-xs text-bny-sky mt-0.5">
          Period: {data.period} · Reviewer: {data.reviewer} · Signed off by:{" "}
          {data.signedOffBy}
        </div>
      </div>
      <div className="text-right">
        <div className="text-[11px] text-bny-mist">Overall</div>
        <div className="text-[22px] font-medium mt-0.5">{data.overall}</div>
        <div className="text-[11px] text-bny-teal">{data.overallSub}</div>
      </div>
    </header>
  );
}
