from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from typing import Any

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


def _strip_pricing_lines(tagged_lines: list[tuple[Any, str]]) -> list[tuple[Any, str]]:
    """Core pricing-skip logic over (tag, line) pairs.

    `tag` is opaque (e.g. a page number, or None) and is only carried through so a
    pricing section that spans a page boundary keeps being skipped correctly — the
    skip/heading-level state must not reset just because the underlying source is
    paginated.
    """
    kept: list[tuple[Any, str]] = []
    skipping = False
    heading_level = 0
    for tag, line in tagged_lines:
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
        kept.append((tag, line))
    return kept


def strip_pricing_content(text: str) -> str:
    """Drop pricing headings and premium lines so they never reach the vector store."""
    tagged = [(None, line) for line in text.splitlines()]
    kept = _strip_pricing_lines(tagged)
    return "\n".join(line for _tag, line in kept).strip() + "\n"


def load_pages(filename: str, content: bytes) -> list[tuple[int | None, str]]:
    """Return (page_number, page_text) pairs.

    PDFs are extracted page-by-page (1-indexed) using pypdf's layout-preserving mode,
    which keeps column whitespace alignment intact so downstream table detection
    (`backend.rag.layout.extract_blocks`) has a chance of recognizing table rows — the
    default extraction mode collapses that alignment. Non-PDF (Markdown) sources have
    no page concept and return a single `(None, text)` pair.

    Pricing-section stripping runs across all pages in one pass (not per page) so a
    pricing section that spans a page break is still fully removed.
    """
    suffix = Path(filename).suffix.lower()
    if suffix != ".pdf":
        raw = content.decode("utf-8")
        return [(None, strip_pricing_content(raw))]

    reader = PdfReader(BytesIO(content))
    tagged_lines: list[tuple[int, str]] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            raw = page.extract_text(extraction_mode="layout") or ""
        except Exception:
            raw = page.extract_text() or ""
        for line in raw.splitlines():
            tagged_lines.append((index, line))

    kept = _strip_pricing_lines(tagged_lines)
    pages: dict[int, list[str]] = {}
    for page_number, line in kept:
        pages.setdefault(page_number, []).append(line)
    return [
        (page_number, "\n".join(lines).strip() + "\n")
        for page_number, lines in sorted(pages.items())
    ]


def load_text(filename: str, content: bytes) -> str:
    return "\n\n".join(text for _page_number, text in load_pages(filename, content))


def read_path(path: Path) -> str:
    return load_text(path.name, path.read_bytes())
