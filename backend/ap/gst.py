"""GST helpers: GSTIN structure, checksum and state codes. Pure functions, no I/O."""
import re

CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
GSTIN_RE = re.compile(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b")
STATES = {"06": "Haryana", "07": "Delhi", "09": "Uttar Pradesh", "27": "Maharashtra", "29": "Karnataka", "33": "Tamil Nadu"}


def checksum_char(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        product = CHARS.index(ch) * (1 if i % 2 == 0 else 2)
        total += product // 36 + product % 36
    return CHARS[(36 - total % 36) % 36]


def make_gstin(state: str, pan: str, entity: str = "1") -> str:
    first14 = f"{state}{pan}{entity}Z"
    return first14 + checksum_char(first14)


def is_valid_gstin(g: str) -> bool:
    return bool(g) and bool(GSTIN_RE.fullmatch(g)) and checksum_char(g[:14]) == g[14]


_TO_DIGIT = str.maketrans({"O": "0", "D": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "B": "8", "G": "6"})
_TO_ALPHA = str.maketrans({"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G"})
_DIGIT_POS, _ALPHA_POS = {0, 1, 7, 8, 9, 10}, {2, 3, 4, 5, 6, 11}


def repair_gstin(token: str):
    """Fix common OCR confusions by position (state code and PAN digits must be digits, PAN letters must be
    letters). Returns the repaired GSTIN only if its checksum then validates, else None."""
    t = token.upper().replace(" ", "")
    if len(t) != 15:
        return None
    chars = [c.translate(_TO_DIGIT) if i in _DIGIT_POS else c.translate(_TO_ALPHA) if i in _ALPHA_POS else c for i, c in enumerate(t)]
    if chars[13] in "2S":
        chars[13] = "Z"
    fixed = "".join(chars)
    return fixed if is_valid_gstin(fixed) else None


def state_of(gstin: str) -> str:
    return gstin[:2] if gstin else ""


def pan_of(gstin: str) -> str:
    return gstin[2:12] if gstin else ""
