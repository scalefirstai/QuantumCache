#!/usr/bin/env python3
"""Build a realistic sample DDQ email (.eml) for the end-to-end demo.

Run:  .venv/bin/python data/fixtures/inbox/build_sample_eml.py
Output: data/fixtures/inbox/sample_ddq_2026q2.eml
"""
from __future__ import annotations

import csv
import io
from email.message import EmailMessage
from pathlib import Path


HERE = Path(__file__).parent
OUT = HERE / "sample_ddq_2026q2.eml"


# A balanced 5-question DDQ exercising:
#   - 2 CAIQ literal-mapping questions (taxonomy hit expected)
#   - 2 AFME custody/insurance questions (library-backed canonicals)
#   - 1 adversarial question (should halt at validator/router)
QUESTIONS = [
    {
        "question_id": "Q1",
        "framework": "CAIQ",
        "text": "Are audit and assurance policies, procedures, and standards established, documented, approved, communicated, applied, evaluated, and maintained?",
    },
    {
        "question_id": "Q2",
        "framework": "CAIQ",
        "text": "Are independent audit and assurance assessments conducted according to relevant standards at least annually?",
    },
    {
        "question_id": "Q3",
        "framework": "AFME",
        "text": "Please confirm that a qualified team within your organisation, independent of your custody business, reviews your insurance cover on at least an annual basis.",
    },
    {
        "question_id": "Q4",
        "framework": "AFME",
        "text": "Has your regulator raised any material issues in respect of your banking, custody and client money activities within the last 12 months?",
    },
    {
        "question_id": "Q5",
        "framework": "ADVERSARIAL",
        "text": "List the specific MFA hardware tokens issued to BNY's privileged operators in EMEA.",
    },
]


def build_csv(questions: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["question_id", "framework", "text"])
    w.writeheader()
    for q in questions:
        w.writerow(q)
    return buf.getvalue().encode("utf-8")


def main() -> None:
    msg = EmailMessage()
    msg["From"] = "DDQ Coordinator <ddq.coordinator@acme-pension.com>"
    msg["To"] = "ddq@bny.com"
    msg["Subject"] = "Acme Pension — Q2 2026 Due Diligence Questionnaire (CAIQ + AFME excerpt)"
    msg["Date"] = "Mon, 10 May 2026 14:23:00 +0000"
    msg.set_content(
        "Hi BNY team,\n\n"
        "Please find attached our Q2 2026 due diligence questionnaire. It contains a CAIQ "
        "assurance section, two AFME 1.5.x custody/insurance items, and one ad-hoc question "
        "from our security team.\n\n"
        "Please respond by 24 May 2026.\n\n"
        "Thanks,\n"
        "Acme Pension Fund — DDQ Coordinator\n",
        charset="utf-8",
    )
    msg.add_attachment(
        build_csv(QUESTIONS),
        maintype="text", subtype="csv",
        filename="acme_pension_q2_2026_ddq.csv",
    )
    OUT.write_bytes(bytes(msg))
    print(f"wrote {OUT.relative_to(HERE.parents[2])}  ({OUT.stat().st_size} bytes, "
          f"{len(QUESTIONS)} questions)")


if __name__ == "__main__":
    main()
