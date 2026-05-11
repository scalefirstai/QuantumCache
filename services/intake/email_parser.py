"""Email intake — ddq.md §L08.

Parses an .eml file (RFC 5322) shipped to the shared inbox `ddq@bny.com`,
extracts attachments, and pulls a question list out of the supported
attachment formats:
- CSV  (columns: question_id, framework, text)
- JSON (list of {question_id, framework, text})
- XLSX (single sheet, same columns) — deferred (requires openpyxl)

Returns a normalized IngestedDDQ record (questions + metadata) that the
orchestrator feeds into the agent pipeline.
"""

from __future__ import annotations

import csv
import datetime as dt
import email
import hashlib
import io
import json
from dataclasses import dataclass, field
from email import policy
from email.message import Message
from pathlib import Path
from typing import Optional


@dataclass
class IngestedQuestion:
    question_id: str
    framework: str
    text: str
    order: int


@dataclass
class IngestedDDQ:
    ddq_id: str
    from_email: str
    to_email: str
    subject: str
    received_at: str
    attachments: list[str] = field(default_factory=list)
    questions: list[IngestedQuestion] = field(default_factory=list)
    raw_eml_sha256: str = ""


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _ddq_id_from(subject: str, from_email: str, ts: str) -> str:
    body = (subject + "|" + from_email + "|" + ts).encode("utf-8")
    return "ddq_" + hashlib.sha1(body).hexdigest()[:12]


def _extract_questions_csv(data: bytes) -> list[IngestedQuestion]:
    reader = csv.DictReader(io.StringIO(data.decode("utf-8")))
    out = []
    for i, row in enumerate(reader):
        qid = (row.get("question_id") or row.get("id") or f"q{i+1}").strip()
        fw = (row.get("framework") or "").strip().upper() or "UNKNOWN"
        txt = (row.get("text") or row.get("question") or "").strip()
        if txt:
            out.append(IngestedQuestion(question_id=qid, framework=fw, text=txt, order=i))
    return out


def _extract_questions_json(data: bytes) -> list[IngestedQuestion]:
    parsed = json.loads(data)
    items = parsed if isinstance(parsed, list) else parsed.get("questions", [])
    out = []
    for i, row in enumerate(items):
        qid = (row.get("question_id") or row.get("id") or f"q{i+1}").strip()
        fw = (row.get("framework") or "").strip().upper() or "UNKNOWN"
        txt = (row.get("text") or row.get("question") or "").strip()
        if txt:
            out.append(IngestedQuestion(question_id=qid, framework=fw, text=txt, order=i))
    return out


def _walk_attachments(msg: Message) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    for part in msg.walk():
        if part.is_multipart():
            continue
        disp = (part.get("Content-Disposition") or "").lower()
        filename = part.get_filename()
        if filename and ("attachment" in disp or "inline" in disp or part.get_content_maintype() != "text"):
            payload = part.get_payload(decode=True) or b""
            out.append((filename, payload))
    return out


def parse_eml(path: Path) -> IngestedDDQ:
    raw = path.read_bytes()
    msg = email.message_from_bytes(raw, policy=policy.default)

    from_email = str(msg.get("From") or "")
    to_email = str(msg.get("To") or "")
    subject = str(msg.get("Subject") or "")
    received_at = str(msg.get("Date") or dt.datetime.now(dt.timezone.utc).isoformat())

    ddq_id = _ddq_id_from(subject, from_email, received_at)
    attachments = _walk_attachments(msg)
    questions: list[IngestedQuestion] = []
    attachment_names: list[str] = []
    for fn, data in attachments:
        attachment_names.append(fn)
        lower = fn.lower()
        if lower.endswith(".csv"):
            questions.extend(_extract_questions_csv(data))
        elif lower.endswith(".json"):
            questions.extend(_extract_questions_json(data))
        # XLSX intentionally deferred — openpyxl is a heavy dep for the demo.

    # Renumber order across attachments.
    for i, q in enumerate(questions):
        q.order = i

    return IngestedDDQ(
        ddq_id=ddq_id,
        from_email=from_email,
        to_email=to_email,
        subject=subject,
        received_at=received_at,
        attachments=attachment_names,
        questions=questions,
        raw_eml_sha256=_sha256(raw),
    )


def parse_email_or_dir(target: Path) -> IngestedDDQ:
    """Convenience: accept an .eml file or a directory containing exactly one .eml."""
    if target.is_dir():
        emls = list(target.glob("*.eml"))
        if not emls:
            raise FileNotFoundError(f"No .eml found in {target}")
        if len(emls) > 1:
            raise RuntimeError(f"Multiple .eml in {target}; pass one explicitly")
        target = emls[0]
    return parse_eml(target)
