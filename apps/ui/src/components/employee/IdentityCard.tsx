import type { EmployeeConsole } from "@/types/employee";

export function IdentityCard({ data }: { data: EmployeeConsole }) {
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
          <div className="text-base font-medium">
            {data.name} · {data.role}
          </div>
          <span className="bg-bny-teal text-white text-[10px] px-2 py-0.5 rounded-full font-medium">
            DIGITAL EMPLOYEE
          </span>
        </div>
        <div className="text-xs text-bny-sky mt-0.5">{data.runDescription}</div>
        <div className="text-[11px] text-bny-mist mt-px">{data.reportingLine}</div>
      </div>
      <div className="text-right">
        <div className="text-[11px] text-bny-mist">Run progress</div>
        <div className="text-[22px] font-medium mt-0.5" data-testid="run-progress">
          {data.progressPct}%
        </div>
        <div className="text-[11px] text-bny-teal">● Live</div>
      </div>
    </header>
  );
}
