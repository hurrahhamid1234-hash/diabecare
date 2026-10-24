"""Checks uploaded files by their real content (first bytes), never by the name or type the browser claims."""
import base64
import binascii
import io
import re
from typing import Optional

from fastapi import HTTPException

BAD_FILE = "Unsupported file. Please use a JPG, PNG, WEBP or PDF"


def sniff_type(data: bytes) -> Optional[str]:
    if data[:5] == b"%PDF-":
        return "application/pdf"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def decode_upload(b64: str, max_bytes: int) -> tuple[bytes, str]:
    """base64 text -> (bytes, mime). Raises 400 / 413 with a plain message."""
    try:
        data = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail=BAD_FILE)
    if not data:
        raise HTTPException(status_code=400, detail=BAD_FILE)
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File is too big. The limit is {max_bytes // (1024 * 1024)} MB")
    mime = sniff_type(data)
    if not mime:
        raise HTTPException(status_code=400, detail=BAD_FILE)
    return data, mime


def clean_name(name: str) -> str:
    name = re.split(r"[\\/]", name)[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return (name or "file")[:150]


def pdf_text(data: bytes, max_pages: int = 8, max_chars: int = 6000) -> str:
    """Text of a PDF made from text (not a scan). Empty string when there is none or the file cannot be read."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            return ""
        parts = []
        for page in reader.pages[:max_pages]:
            parts.append(page.extract_text() or "")
            if sum(len(p) for p in parts) >= max_chars:
                break
        return re.sub(r"\n{3,}", "\n\n", "\n".join(parts)).strip()[:max_chars]
    except Exception:
        return ""