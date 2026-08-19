"""Format extractors (T-05-05, plan §18.3): text extraction per file type.

Deterministic and dependency-minimal:

- ``.txt/.rst/.csv`` — plain text read
- ``.md`` — Markdown syntax stripped (regex-based: deterministic, não é um
  parser MD completo — strip conservador de markers estruturais)
- ``.py/.json/.yaml/.yml`` — code/markup passthrough
- ``.html/.htm`` — tags removidas via stdlib ``html.parser`` (script/style dropados)
- ``.pdf`` — via ``pypdf`` (dependência OPCIONAL); ausente => ``ExtractionError``
  explícito. Extração NUNCA é silenciosamente falsa: ou sai texto real, ou falha
  declarada.

Falhas são surfacadas pelo chamador (FileCorpus registra em
``extraction_failures``) — documento não-extraível não entra no índice nem
vira "fonte fantasma".
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path


class ExtractionError(Exception):
    """Falha explícita de extração (formato, dependência ou IO)."""


# --------------------------------------------------------------------------- #
# Plain / code (sem transformação estrutural)
# --------------------------------------------------------------------------- #
def _extract_plain(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# --------------------------------------------------------------------------- #
# Markdown: strip conservador de markers
# --------------------------------------------------------------------------- #
_MD_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_MD_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_MARKER_RE = re.compile(r"(?m)^#{1,6}\s+|\*\*|__|(?<!\w)\*|\b_")


def _extract_markdown(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    text = _MD_FENCE_RE.sub(" ", text)  # code fences fora (não são prosa citável)
    text = _MD_IMG_RE.sub(" ", text)  # imagens não carregam texto
    text = _MD_LINK_RE.sub(r"\1", text)  # [texto](url) -> texto
    text = _MD_MARKER_RE.sub("", text)  # headings/ênfases
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# --------------------------------------------------------------------------- #
# HTML: stdlib parser, sem dependências
# --------------------------------------------------------------------------- #
class _TextHTMLParser(HTMLParser):
    """Coleta texto visível; ignora script/style/head-only tokens."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "template", "head"}:
            self._skip_depth += 1
        elif tag in {"br", "p", "div", "section", "article", "li", "tr"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if (
            tag in {"script", "style", "noscript", "template", "head"}
            and self._skip_depth
        ):
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and data.strip():
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def html_to_text(text: str) -> str:
    """Strip determinístico de HTML (string -> texto visível).

    API pública: usada pelo extractor de arquivos e pelos web adapters
    (adapters.py) — sem hack de Path fake.
    """
    parser = _TextHTMLParser()
    parser.feed(text)
    return re.sub(r"\n{3,}", "\n\n", parser.text()).strip()


def _extract_html(path: Path) -> str:
    try:
        return html_to_text(path.read_text(encoding="utf-8", errors="replace"))
    except OSError as exc:
        raise ExtractionError(f"IO falhou em {path.name}: {exc}") from exc


# --------------------------------------------------------------------------- #
# PDF: dependência opcional pypdf — falha declarada quando ausente
# --------------------------------------------------------------------------- #
def _extract_pdf(path: Path) -> str:
    import importlib.util

    if importlib.util.find_spec("pypdf") is None:
        raise ExtractionError(
            "PDF requer a dependência opcional `pypdf` (pip install pypdf). "
            "Extração NÃO é simulada: instale pypdf ou remova o PDF do corpus."
        )
    from pypdf import PdfReader  # type: ignore[import-not-found]

    try:
        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise ExtractionError(f"PDF parse falhou em {path.name}: {exc}") from exc
    return "\n\n".join(p.strip() for p in pages if p.strip())


# --------------------------------------------------------------------------- #
# Dispatch por extensão
# --------------------------------------------------------------------------- #
_EXTRACTORS: dict[str, tuple[str, "callable"]] = {}


def _register() -> dict[str, tuple[str, object]]:
    return {
        ".txt": ("plain", _extract_plain),
        ".rst": ("plain", _extract_plain),
        ".csv": ("plain", _extract_plain),
        ".log": ("plain", _extract_plain),
        ".py": ("code", _extract_plain),
        ".json": ("code", _extract_plain),
        ".yaml": ("code", _extract_plain),
        ".yml": ("code", _extract_plain),
        ".md": ("markdown", _extract_markdown),
        ".markdown": ("markdown", _extract_markdown),
        ".html": ("html", _extract_html),
        ".htm": ("html", _extract_html),
        ".pdf": ("pdf", _extract_pdf),
    }


_EXTRACTORS = _register()

EXTRACTABLE_EXTENSIONS: frozenset[str] = frozenset(_EXTRACTORS)


def extract_text(path: str | Path) -> tuple[str, str]:
    """Extrai texto de ``path``; retorna ``(texto, nome_do_extractor)``.

    Raises:
        ExtractionError: extensão não suportada, dependência ausente ou
            parse falhou — o chamador DEVE surfacar, nunca engolir.
    """
    path = Path(path)
    ext = path.suffix.lower()
    entry = _EXTRACTORS.get(ext)
    if entry is None:
        raise ExtractionError(f"extensão não extraível: {ext or path.name}")
    name, fn = entry
    try:
        text = fn(path)
    except OSError as exc:
        raise ExtractionError(f"IO falhou em {path.name}: {exc}") from exc
    return text, name
