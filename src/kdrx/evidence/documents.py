"""Document IR preserving original text coordinates and format blocks."""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import Field

from kdrx.schemas.versioning import VersionedModel


def source_id(uri: str) -> str:
    return "SRC-" + hashlib.sha256(uri.encode("utf-8")).hexdigest()[:32]


class DocumentBlock(VersionedModel):
    block_id: str
    kind: Literal["text", "code", "table", "figure"] = "text"
    text: str
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    page: int | None = Field(default=None, ge=1)


class DocumentIR(VersionedModel):
    source_id: str
    revision: str
    raw_bytes_hash: str
    extracted_text_hash: str
    extractor: str
    extractor_version: str = "0.3"
    text: str
    blocks: list[DocumentBlock]

    def verify(self) -> bool:
        return hashlib.sha256(
            self.text.encode("utf-8")
        ).hexdigest() == self.extracted_text_hash and all(
            self.text[b.char_start : b.char_end] == b.text for b in self.blocks
        )


def document_ir(uri: str, raw: bytes, text: str, extractor: str) -> DocumentIR:
    blocks = []
    offset = 0
    code = False
    for i, line in enumerate(text.splitlines(keepends=True)):
        if line.lstrip().startswith(("```", "~~~")):
            code = not code
            kind = "code"
        else:
            kind = "code" if code else "table" if "|" in line else "text"
        blocks.append(
            DocumentBlock(
                block_id=f"B-{i}",
                kind=kind,
                text=line,
                char_start=offset,
                char_end=offset + len(line),
            )
        )
        offset += len(line)
    raw_hash = hashlib.sha256(raw).hexdigest()
    text_hash = hashlib.sha256(text.encode()).hexdigest()
    return DocumentIR(
        source_id=source_id(uri),
        revision=hashlib.sha256(
            (raw_hash + text_hash + extractor + "0.3").encode()
        ).hexdigest(),
        raw_bytes_hash=raw_hash,
        extracted_text_hash=text_hash,
        extractor=extractor,
        text=text,
        blocks=blocks,
    )
