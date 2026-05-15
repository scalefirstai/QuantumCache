import { useEffect, useState } from "react";
import {
  decideApproval,
  getApproval,
  getBundle,
  getJournal,
  replayDeal,
  requestApproval,
  sealDeal,
} from "@/api/oppDeal";
import type {
  ApprovalRequest,
  DealJournalEvent,
  Opportunity,
  ReplayReport,
  SealedDealBundle,
} from "@/types/oppDeal";
import { PrimaryButton, SecondaryButton } from "@/components/datasets/Common";
import { Card, KeyValueGrid, Empty } from "./Format";

export function StageS08({ opp }: { opp: Opportunity }) {
  const [req, setReq] = useState<ApprovalRequest | null>(null);
  const [bundle, setBundle] = useState<SealedDealBundle | null>(null);
  const [replay, setReplay] = useState<ReplayReport | null>(null);
  const [journal, setJournal] = useState<DealJournalEvent[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const reload = async () => {
    try {
      const r = await getApproval(opp.opportunity_id).catch(() => null);
      setReq(r);
    } catch { /* ignore */ }
    try {
      const b = await getBundle(opp.opportunity_id).catch(() => null);
      setBundle(b);
    } catch { /* ignore */ }
    try {
      const j = await getJournal(opp.opportunity_id);
      setJournal(j);
    } catch { /* ignore */ }
  };

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opp.opportunity_id, opp.deal_id, opp.status]);

  const onRequest = async () => {
    setErr(null);
    try {
      setReq(await requestApproval(opp.opportunity_id));
    } catch (e) {
      setErr(String(e));
    }
  };

  const onDecide = async (role: string) => {
    setErr(null);
    try {
      const updated = await decideApproval(opp.opportunity_id, role, `u_${role}`, "approved via UI");
      setReq(updated);
    } catch (e) {
      setErr(String(e));
    }
  };

  const onSeal = async () => {
    setErr(null);
    try {
      const b = await sealDeal(opp.opportunity_id);
      setBundle(b);
      await reload();
    } catch (e) {
      setErr(String(e));
    }
  };

  const onReplay = async () => {
    setErr(null);
    try {
      setReplay(await replayDeal(opp.opportunity_id));
    } catch (e) {
      setErr(String(e));
    }
  };

  const decidedRoles = new Set((req?.decisions ?? []).map((d) => d.role));
  const allApproved = req?.state === "approved";

  return (
    <section data-testid="stage-s08">
      <Card
        title="S08 · Approval"
        testId="card-s08-approval"
        actions={
          !req ? (
            <PrimaryButton onClick={onRequest} testId="request-approval-btn">
              Request approval
            </PrimaryButton>
          ) : null
        }
      >
        {err && <div className="text-sm text-bny-danger mb-3" data-testid="s08-error">{err}</div>}
        {!req ? (
          <Empty>
            Pricing (S06) + operating model (S07) must be complete. Approval
            tier is policy-derived from complexity + deal NPV.
          </Empty>
        ) : (
          <>
            <KeyValueGrid
              items={[
                { label: "Request id", value: req.request_id, testId: "kv-request-id" },
                { label: "Tier required", value: req.tier_required, testId: "kv-tier-required" },
                {
                  label: "Approvers required",
                  value: req.approvers_required.join(", "),
                },
                { label: "State", value: req.state, testId: "kv-approval-state" },
                { label: "Decisions", value: req.decisions.length.toString() },
              ]}
            />
            <div className="mt-4 flex flex-wrap gap-2" data-testid="approval-actions">
              {req.approvers_required.map((role) => (
                <SecondaryButton
                  key={role}
                  testId={`approve-${role}`}
                  onClick={() => onDecide(role)}
                >
                  {decidedRoles.has(role) ? `✓ ${role}` : `Approve as ${role}`}
                </SecondaryButton>
              ))}
            </div>
            {req.decisions.length > 0 && (
              <ul className="text-xs text-bny-slate mt-3 space-y-0.5" data-testid="approval-decisions">
                {req.decisions.map((d, idx) => (
                  <li key={idx}>
                    ✓ {d.role} · {d.user_id} · {d.ts} ·{" "}
                    <span className="font-mono">{d.signature}</span>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </Card>

      <Card
        title="Seal & handoff"
        testId="card-s08-seal"
        actions={
          allApproved && !bundle ? (
            <PrimaryButton onClick={onSeal} testId="seal-btn">
              Seal deal
            </PrimaryButton>
          ) : bundle ? (
            <SecondaryButton onClick={onReplay} testId="replay-btn">
              Replay & verify
            </SecondaryButton>
          ) : null
        }
      >
        {!bundle ? (
          <Empty>
            Once every required approver has signed, sealing writes the
            immutable bundle (S3 Object Lock equivalent) and fires handoffs to
            contracting, implementation, capacity planning, and HR.
          </Empty>
        ) : (
          <>
            <KeyValueGrid
              items={[
                { label: "Deal id", value: bundle.deal_id, testId: "kv-deal-id" },
                { label: "Sealed at", value: bundle.sealed_at },
                { label: "Platform version", value: bundle.platform_version },
                { label: "Approvers", value: bundle.approval_chain.length.toString() },
                {
                  label: "Merkle root",
                  value: (
                    <span className="font-mono text-xs break-all" data-testid="merkle-root">
                      {bundle.merkle_root}
                    </span>
                  ),
                },
                {
                  label: "Handoffs",
                  value: bundle.handoff_targets.join(", "),
                  testId: "kv-handoffs",
                },
              ]}
            />
            {replay && (
              <div className="mt-4" data-testid="replay-result">
                <div className="text-[10px] uppercase tracking-wider text-bny-fog mb-1">
                  Replay verification
                </div>
                <div
                  className={
                    "text-sm font-medium " + (replay.ok ? "text-bny-ok" : "text-bny-danger")
                  }
                >
                  {replay.ok ? "✓ All hashes verify · bit-exact replay" : "✗ Replay mismatch"}
                </div>
                <ul className="text-xs mt-2 space-y-0.5">
                  {replay.checks &&
                    Object.entries(replay.checks).map(([k, v]) => (
                      <li key={k} className={v ? "text-bny-slate" : "text-bny-danger"}>
                        {v ? "✓" : "✗"} {k}
                      </li>
                    ))}
                </ul>
              </div>
            )}
          </>
        )}
      </Card>

      <Card title="Deal journal" testId="card-s08-journal">
        <div className="text-xs text-bny-slate mb-2">
          {journal.length} hash-chained events for this opportunity.
        </div>
        <div
          className="max-h-72 overflow-y-auto border border-bny-mist rounded-md"
          data-testid="journal-scroll"
        >
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-bny-paper text-[10px] uppercase tracking-wider text-bny-fog">
              <tr>
                <th className="py-1.5 px-2 text-left">Kind</th>
                <th className="text-left">Actor</th>
                <th className="text-left">Timestamp</th>
                <th className="text-left">Chain hash</th>
              </tr>
            </thead>
            <tbody>
              {journal.map((e) => (
                <tr
                  key={e.event_id}
                  className="border-b border-bny-mist/40"
                  data-testid={`journal-row-${e.event_id}`}
                >
                  <td className="py-1 px-2 font-mono">{e.kind}</td>
                  <td>{e.actor_role}</td>
                  <td className="font-mono">{e.ts}</td>
                  <td className="font-mono truncate max-w-[180px]">{e.chain_hash}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </section>
  );
}
