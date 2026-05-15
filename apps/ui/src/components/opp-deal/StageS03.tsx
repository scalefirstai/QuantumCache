import { useEffect, useState } from "react";
import { getCommitments, setCommitments } from "@/api/oppDeal";
import type { Commitment, CommitmentClass, CommitmentSet, Opportunity } from "@/types/oppDeal";
import { PrimaryButton, SecondaryButton, Modal, FormField, Input, Select, TextArea } from "@/components/datasets/Common";
import { Card, Empty } from "./Format";

const COMMITMENT_CLASSES: CommitmentClass[] = [
  "sla", "control", "jurisdiction_coverage", "data_residency", "reporting", "other",
];

export function StageS03({ opp }: { opp: Opportunity }) {
  const [cs, setCs] = useState<CommitmentSet | null>(null);
  const [open, setOpen] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // form state
  const [ddqRun, setDdqRun] = useState(`run_${opp.opportunity_id.slice(-12)}`);
  const [cls, setCls] = useState<CommitmentClass>("sla");
  const [canonical, setCanonical] = useState("canon.or.business_continuity.rto");
  const [text, setText] = useState("");
  const [material, setMaterial] = useState(true);
  const [schedule, setSchedule] = useState("schedule_b.sla");

  useEffect(() => {
    getCommitments(opp.opportunity_id).then(setCs).catch((e) => setErr(String(e)));
  }, [opp.opportunity_id]);

  const onAdd = async () => {
    if (!text.trim()) return;
    setErr(null);
    try {
      const existing: Commitment[] = cs?.commitments ?? [];
      const body = {
        ddq_run_id: ddqRun,
        commitments: [
          ...existing.map((c) => ({
            commitment_id: c.commitment_id,
            canonical_id: c.canonical_id,
            commitment_text: c.commitment_text,
            commitment_class: c.commitment_class,
            material: c.material,
            contract_schedule_target: c.contract_schedule_target,
            library_entry_hash: c.library_entry_hash,
          })),
          {
            canonical_id: canonical,
            commitment_text: text,
            commitment_class: cls,
            material,
            contract_schedule_target: schedule,
            library_entry_hash: "sha256:operator-add",
          },
        ],
      };
      const next = await setCommitments(opp.opportunity_id, body);
      setCs(next);
      setOpen(false);
      setText("");
    } catch (e) {
      setErr(String(e));
    }
  };

  return (
    <section data-testid="stage-s03">
      <Card
        title="S03 · DDQ commitments"
        testId="card-s03"
        actions={
          <PrimaryButton onClick={() => setOpen(true)} testId="add-commitment-btn">
            Add commitment
          </PrimaryButton>
        }
      >
        {err && <div className="text-sm text-bny-danger mb-3">{err}</div>}
        {!cs || cs.commitments.length === 0 ? (
          <Empty>
            No DDQ commitments linked yet. Material commitments (SLAs, controls,
            data-residency, jurisdiction) flow into the contract schedule via
            the operating-model cross-check (S07).
          </Empty>
        ) : (
          <>
            <div className="text-xs text-bny-slate mb-2" data-testid="ddq-run-id">
              DDQ run: <span className="font-mono">{cs.ddq_run_id}</span> ·{" "}
              {cs.commitments.length} commitments
            </div>
            <table className="w-full text-sm" data-testid="commitments-table">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wider text-bny-fog border-b border-bny-mist">
                  <th className="py-1.5">Canonical</th>
                  <th>Class</th>
                  <th>Material</th>
                  <th>Schedule</th>
                  <th>Text</th>
                </tr>
              </thead>
              <tbody>
                {cs.commitments.map((c) => (
                  <tr
                    key={c.commitment_id}
                    className="border-b border-bny-mist/40"
                    data-testid={`commitment-row-${c.commitment_id}`}
                  >
                    <td className="py-1.5 font-mono text-xs">{c.canonical_id}</td>
                    <td className="text-xs">{c.commitment_class}</td>
                    <td className="text-xs">{c.material ? "yes" : "no"}</td>
                    <td className="text-xs">{c.contract_schedule_target}</td>
                    <td className="text-xs">{c.commitment_text}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </Card>

      <Modal
        open={open}
        title="Add DDQ commitment"
        onClose={() => setOpen(false)}
        testId="add-commitment-modal"
      >
        <FormField label="DDQ run id">
          <Input
            value={ddqRun}
            onChange={(e) => setDdqRun(e.target.value)}
            data-testid="cm-ddq-run"
          />
        </FormField>
        <FormField label="Canonical id">
          <Input
            value={canonical}
            onChange={(e) => setCanonical(e.target.value)}
            data-testid="cm-canonical"
          />
        </FormField>
        <FormField label="Class">
          <Select
            value={cls}
            onChange={(e) => setCls(e.target.value as CommitmentClass)}
            data-testid="cm-class"
          >
            {COMMITMENT_CLASSES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField label="Commitment text">
          <TextArea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={3}
            data-testid="cm-text"
          />
        </FormField>
        <FormField label="Contract schedule target">
          <Input
            value={schedule}
            onChange={(e) => setSchedule(e.target.value)}
            data-testid="cm-schedule"
          />
        </FormField>
        <label className="text-sm flex items-center gap-2 mb-3">
          <input
            type="checkbox"
            checked={material}
            onChange={(e) => setMaterial(e.target.checked)}
            data-testid="cm-material"
          />
          Material (flows to operating-model cross-check and contract)
        </label>
        <div className="flex justify-end gap-2">
          <SecondaryButton onClick={() => setOpen(false)}>Cancel</SecondaryButton>
          <PrimaryButton onClick={onAdd} testId="cm-submit">Add commitment</PrimaryButton>
        </div>
      </Modal>
    </section>
  );
}
