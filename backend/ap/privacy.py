"""Reversible masking before any text leaves for a model. GSTINs are left as they are: they are public
business identifiers and are needed for matching (note: a GSTIN embeds the PAN, so PAN masking alone
would be theatre)."""
import re

PATTERNS = [
    ("EMAIL", r"[\w.+-]+@[\w-]+\.[\w.]+"),
    ("PHONE", r"\+91[\s-]?\d{2,5}[\s-]?\d{3,5}[\s-]?\d{3,5}"),
    ("IFSC", r"\b[A-Z]{4}0[A-Z0-9]{6}\b"),
    ("BANK", r"(?<=A/c No: )\d{9,18}|(?<=A/c No\. )\d{9,18}|(?<=A/c )\d{9,18}"),
    ("PAN", r"(?<![0-9A-Z])[A-Z]{5}\d{4}[A-Z](?![0-9A-Z])"),
]


def mask(text: str):
    mapping, counts = {}, {}
    for label, pat in PATTERNS:
        def sub(m):
            counts[label] = counts.get(label, 0) + 1
            token = f"[{label}_{counts[label]}]"
            mapping[token] = m.group(0)
            return token
        text = re.sub(pat, sub, text)
    return text, mapping


def unmask(value: str, mapping: dict) -> str:
    for token, real in mapping.items():
        value = value.replace(token, real)
    return value
