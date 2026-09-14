from __future__ import annotations

import re
from itertools import groupby
from typing import TypedDict

_PIPE_TABLE_LINE = re.compile(r"^\s*\|.*\|\s*$")
_MULTI_SPACE_RUN = re.compile(r" {3,}")


class Block(TypedDict):
    type: str  # "table" | "prose"
    text: str


def _is_pipe_table_line(line: str) -> bool:
    return bool(_PIPE_TABLE_LINE.match(line))


def _is_whitespace_table_line(line: str) -> bool:
    """Naive PDF text extraction renders table columns as runs of spaces.

    Two or more such runs on one line suggests column alignment (e.g.
    "Deductible          $500          $1000").
    """
    if not line.strip():
        return False
    return len(_MULTI_SPACE_RUN.findall(line)) >= 2


def _is_table_line(line: str) -> bool:
    return _is_pipe_table_line(line) or _is_whitespace_table_line(line)


def extract_blocks(text: str) -> list[Block]:
    """Split text into ordered prose/table blocks so a table is never split mid-row.

    Detects two table shapes: markdown pipe tables (contiguous ``| ... |`` lines) and
    whitespace-aligned tables typical of naive PDF text extraction (contiguous lines
    with 2+ runs of 3+ spaces). A single isolated table-like line is treated as a
    coincidence (e.g. an indented sentence) rather than a real table — only runs of 2+
    consecutive matching lines count. Everything else is a "prose" block, in original
    order. Adjacent blocks of the same kind are merged.
    """
    lines = text.splitlines(keepends=True)
    if not lines:
        return []

    blocks: list[Block] = []
    for is_table_run, group in groupby(lines, key=_is_table_line):
        group_lines = list(group)
        kind = "table" if (is_table_run and len(group_lines) >= 2) else "prose"
        content = "".join(group_lines)
        if not content.strip():
            kind = "prose"
        if blocks and blocks[-1]["type"] == kind:
            blocks[-1]["text"] += content
        else:
            blocks.append({"type": kind, "text": content})

    return [block for block in blocks if block["text"].strip()]
