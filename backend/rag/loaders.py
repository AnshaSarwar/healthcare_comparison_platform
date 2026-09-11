from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

_PRICING_HEADING = re.compile(
    r"^(#{1,6})\s+.*\b(pricing|premiums|rate\s*card|price list)\b",
    re.IGNORECASE,
)
_PRICING_LINE = re.compile(
    r"(monthly_premium|premium per employee|per employee per month|"
    r"confidential (monthly )?premiums|confidential figures)",
    re.IGNORECASE,
)


def strip_pricing_content(text: str) -> str:
    """Drop pricing headings and premium lines so they never reach the vector store."""
    lines = text.splitlines()
    kept: list[str] = []
    skipping = False
    heading_level = 0
    for line in lines:
        heading = re.match(r"^(#{1,6})\s+", line)
        if skipping:
            if heading and len(heading.group(1)) <= heading_level:
                skipping = False
            else:
                continue
        if heading and _PRICING_HEADING.search(line):
            skipping = True
            heading_level = len(heading.group(1))
            continue
        if _PRICING_LINE.search(line):
            continue
        kept.append(line)
    return "\n".join(kept).strip() + "\n"


def load_text(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(BytesIO(content))
        raw = "\n\n".join((page.extract_text() or "") for page in reader.pages)
    else:
        raw = content.decode("utf-8")
    return strip_pricing_content(raw)


def read_path(path: Path) -> str:
    return load_text(path.name, path.read_bytes())
