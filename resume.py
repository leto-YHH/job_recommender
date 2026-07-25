"""履歷讀取模組:支援 .pdf / .docx / .txt / .md"""
from pathlib import Path

SUPPORTED_SUFFIXES = (".pdf", ".docx", ".txt", ".md")


def read_resume(path: str) -> str:
    """讀取履歷檔案,回傳純文字內容"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"找不到履歷檔案:{path}")

    suffix = p.suffix.lower()
    if suffix == ".pdf":
        text = _read_pdf(p)
    elif suffix == ".docx":
        text = _read_docx(p)
    elif suffix in (".txt", ".md"):
        text = p.read_text(encoding="utf-8")
    else:
        raise ValueError(
            f"不支援的履歷格式:{suffix}"
            f"(支援 {', '.join(SUPPORTED_SUFFIXES)})"
        )

    text = text.strip()
    if not text:
        raise ValueError(
            f"從 {path} 讀不到任何文字內容"
            "(若是掃描版 PDF,裡面可能只有圖片,沒有文字層)"
        )
    return text


def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _read_docx(path: Path) -> str:
    import docx

    doc = docx.Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
