import type { Pipeline } from "@/types/pipeline";

function shortHash(h: string | undefined, n = 12): string {
  if (!h) return "—";
  return h.split(":").pop()!.slice(0, n);
}

export function EmailHeader({ pipeline }: { pipeline: Pipeline }) {
  return (
    <div
      data-testid="pipeline-email-header"
      className="bg-white border border-bny-mist rounded-lg px-4 py-3"
    >
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <div className="text-[11px] uppercase tracking-wider text-bny-fog font-medium mb-1">
            Inbox · ddq@bny.com
          </div>
          <div className="text-sm font-medium text-bny-ink truncate">
            {pipeline.subject}
          </div>
          <div className="text-[12px] text-bny-slate mt-0.5 truncate">
            From <span className="font-mono">{pipeline.from}</span> · sealed{" "}
            {pipeline.sealedAt.slice(0, 19)}Z
          </div>
        </div>
        <div className="text-right text-[11px] text-bny-fog shrink-0 leading-tight">
          <div>
            <span className="font-mono">{pipeline.ddqId}</span>
          </div>
          <div>
            eml · <span className="font-mono">{shortHash(pipeline.rawEmlSha256)}</span>
          </div>
          <div>
            {pipeline.questionCount} question{pipeline.questionCount === 1 ? "" : "s"} · {pipeline.platformVersion}
          </div>
        </div>
      </div>
    </div>
  );
}
