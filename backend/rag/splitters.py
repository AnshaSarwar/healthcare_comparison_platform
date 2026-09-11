from __future__ import annotations

from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

PARENT_CHUNK_SIZE = 1500
PARENT_CHUNK_OVERLAP = 150
CHILD_CHUNK_SIZE = 400
CHILD_CHUNK_OVERLAP = 80


def split_for_parent_child(text: str, base_meta: dict) -> list[Document]:
    """Small child chunks for retrieval; parent text stored for generation (small-to-big)."""
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
        parents = parent_splitter.split_text(section.page_content) or [section.page_content]
        for parent_index, parent_text in enumerate(parents):
            parent_id = f"{base_meta['document_id']}:{section_name}:{parent_index}"
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
