import { useState } from "react";
import {
  FormField,
  Input,
  Modal,
  PrimaryButton,
  SecondaryButton,
  TextArea,
} from "@/components/datasets/Common";

export function ApprovalModal({
  open,
  title,
  variant,
  onClose,
  onSubmit,
}: {
  open: boolean;
  title: string;
  variant: "approve" | "reject";
  onClose: () => void;
  onSubmit: (decision: { approver: string; rationale: string }) => Promise<void>;
}) {
  const [approver, setApprover] = useState("");
  const [rationale, setRationale] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setErr(null);
    try {
      await onSubmit({ approver, rationale });
      setApprover("");
      setRationale("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Submit failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title={title} testId={`${variant}-modal`}>
      <form onSubmit={submit}>
        <FormField label="Approver" hint="Your name or SME handle">
          <Input
            required
            value={approver}
            onChange={(e) => setApprover(e.target.value)}
            data-testid={`${variant}-approver`}
          />
        </FormField>
        <FormField label="Rationale" hint="Captured in the audit trail">
          <TextArea
            required
            rows={3}
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
            data-testid={`${variant}-rationale`}
          />
        </FormField>
        {err && (
          <div role="alert" className="text-xs text-bny-danger mt-2">
            {err}
          </div>
        )}
        <div className="flex items-center justify-end gap-2 mt-4">
          <SecondaryButton onClick={onClose}>Cancel</SecondaryButton>
          <PrimaryButton
            type="submit"
            disabled={submitting}
            testId={`${variant}-submit`}
          >
            {submitting ? "Saving…" : variant === "approve" ? "Approve" : "Reject"}
          </PrimaryButton>
        </div>
      </form>
    </Modal>
  );
}
