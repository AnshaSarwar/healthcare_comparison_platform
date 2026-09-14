from __future__ import annotations

from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from backend.rag.layout import extract_blocks

PARENT_CHUNK_SIZE = 1500
PARENT_CHUNK_OVERLAP = 150
CHILD_CHUNK_SIZE = 400
CHILD_CHUNK_OVERLAP = 80


def split_for_parent_child(text: str, base_meta: dict) -> list[Document]:
    """Small child chunks for retrieval; parent text stored for generation (small-to-big).

    Table blocks (markdown pipe tables, or whitespace-aligned tables from layout-mode
    PDF extraction — see `backend.rag.layout.extract_blocks`) are kept as a single,
    unsplit chunk each: a table is never fed through the recursive character splitter,
    which has no notion of row/column boundaries and would otherwise cut it mid-row. An
    oversized table chunk is an accepted tradeoff over a corrupted one.
    """
    md_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "title"), ("##", "section")],
    )
    try:
        sections = md_splitter.split_text(text)
    except Exception:
        sections = []
    if not sections:
        sections = [Document(page_content=text, metadata={})]

    parent_splitter = RecursiveCharacterTextSplitter(
        chunk_size=PARENT_CHUNK_SIZE,
        chunk_overlap=PARENT_CHUNK_OVERLAP,
    )
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHILD_CHUNK_SIZE,
        chunk_overlap=CHILD_CHUNK_OVERLAP,
    )

    children: list[Document] = []
    for section in sections:
        section_name = (
            section.metadata.get("section")
            or section.metadata.get("title")
            or "body"
        )
        parent_index = 0
        for block in extract_blocks(section.page_content):
            if block["type"] == "table":
                parent_id = (
                    f"{base_meta['document_id']}:{base_meta.get('page_number')}:"
                    f"{section_name}:{parent_index}"
                )
                parent_index += 1
                children.append(
                    Document(
                        page_content=block["text"],
                        metadata={
                            **base_meta,
                            "section": section_name,
                            "parent_id": parent_id,
                            "parent_text": block["text"],
                            "chunk_index": 0,
                            "kind": "table",
                        },
                    )
                )
                continue

            parents = parent_splitter.split_text(block["text"]) or [block["text"]]
            for parent_text in parents:
                parent_id = (
                    f"{base_meta['document_id']}:{base_meta.get('page_number')}:"
                    f"{section_name}:{parent_index}"
                )
                parent_index += 1
                child_texts = child_splitter.split_text(parent_text) or [parent_text]
                for chunk_index, child_text in enumerate(child_texts):
                    children.append(
                        Document(
                            page_content=child_text,
                            metadata={
                                **base_meta,
                                "section": section_name,
                                "parent_id": parent_id,
                                "parent_text": parent_text,
                                "chunk_index": chunk_index,
                                "kind": "child",
                            },
                        )
                    )
    return children
