"""Turn an incoming email or upload into stored files with provenance (sender, time, message ID, hash)."""
import hashlib
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime

from .db import STORAGE, now, save_file

EXT = {"pdf": ".pdf", "jpg": ".jpg", "png": ".png", "docx": ".docx"}


def kind_of(data: bytes, filename: str) -> str:
    if data[:4] == b"%PDF":
        return "pdf"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:2] == b"PK" and filename.lower().endswith(".docx"):
        return "docx"
    if filename.lower().endswith(".eml") or b"\nFrom:" in data[:2000] or data[:5] == b"From:":
        return "eml"
    return "unknown"


def store(data: bytes, kind: str) -> tuple[str, str]:
    sha = hashlib.sha256(data).hexdigest()
    STORAGE.mkdir(parents=True, exist_ok=True)
    path = STORAGE / f"{sha[:16]}{EXT.get(kind, '.bin')}"
    path.write_bytes(data)
    save_file(path)
    return sha, str(path)


def parse_eml(data: bytes) -> dict:
    msg = BytesParser(policy=policy.default).parsebytes(data)
    sender = msg["From"].addresses[0].addr_spec if msg["From"] and msg["From"].addresses else str(msg["From"] or "")
    try:
        received = parsedate_to_datetime(msg["Date"]).isoformat(timespec="seconds")
    except Exception:
        received = now()
    attachments = []
    for part in msg.iter_attachments():
        payload = part.get_payload(decode=True) or b""
        attachments.append((part.get_filename() or "attachment", payload))
    body = msg.get_body(preferencelist=("plain",))
    return dict(sender=sender.lower(), subject=str(msg["Subject"] or ""), received_at=received,
                message_id=str(msg["Message-ID"] or ""), body=body.get_content() if body else "", attachments=attachments)
