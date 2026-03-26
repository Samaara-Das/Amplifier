"""Supabase Storage helper for campaign asset uploads (images, files)."""

import logging
import os
import uuid
from io import BytesIO

from app.core.config import get_settings

logger = logging.getLogger(__name__)

BUCKET = "campaign-assets"


def _get_storage_client():
    """Get Supabase Storage client. Returns None if not configured."""
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_key:
        logger.warning("Supabase Storage not configured (SUPABASE_URL / SUPABASE_SERVICE_KEY missing)")
        return None
    from supabase import create_client
    client = create_client(settings.supabase_url, settings.supabase_service_key)
    return client.storage


def upload_file(file_bytes: bytes, filename: str, content_type: str, folder: str = "uploads") -> str | None:
    """Upload a file to Supabase Storage and return the public URL.

    Args:
        file_bytes: Raw file content
        filename: Original filename (used for extension)
        content_type: MIME type (e.g. "image/png", "application/pdf")
        folder: Storage subfolder (default: "uploads")

    Returns:
        Public URL string, or None if upload failed
    """
    storage = _get_storage_client()
    if not storage:
        return None

    # Generate unique path to avoid collisions
    ext = os.path.splitext(filename)[1] or ""
    unique_name = f"{uuid.uuid4().hex}{ext}"
    path = f"{folder}/{unique_name}"

    try:
        storage.from_(BUCKET).upload(
            path=path,
            file=file_bytes,
            file_options={"content-type": content_type},
        )
        # Get public URL
        settings = get_settings()
        public_url = f"{settings.supabase_url}/storage/v1/object/public/{BUCKET}/{path}"
        return public_url
    except Exception as e:
        logger.error("Failed to upload %s to Supabase Storage: %s", filename, e)
        return None


def delete_file(path: str) -> bool:
    """Delete a file from Supabase Storage by its path within the bucket."""
    storage = _get_storage_client()
    if not storage:
        return False
    try:
        storage.from_(BUCKET).remove([path])
        return True
    except Exception as e:
        logger.error("Failed to delete %s: %s", path, e)
        return False


def extract_text_from_file(file_bytes: bytes, filename: str, content_type: str) -> str:
    """Extract readable text from uploaded files (PDF, DOCX, TXT).

    Returns extracted text or empty string if extraction fails.
    """
    text = ""
    lower = filename.lower()

    try:
        if lower.endswith(".pdf") or content_type == "application/pdf":
            from PyPDF2 import PdfReader
            reader = PdfReader(BytesIO(file_bytes))
            pages = []
            for page in reader.pages[:50]:  # Cap at 50 pages
                page_text = page.extract_text()
                if page_text:
                    pages.append(page_text.strip())
            text = "\n\n".join(pages)

        elif lower.endswith(".docx") or content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            from docx import Document
            doc = Document(BytesIO(file_bytes))
            paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            text = "\n\n".join(paragraphs)

        elif lower.endswith(".txt") or content_type.startswith("text/"):
            text = file_bytes.decode("utf-8", errors="ignore")

        else:
            logger.info("Unsupported file type for text extraction: %s (%s)", filename, content_type)

    except Exception as e:
        logger.warning("Failed to extract text from %s: %s", filename, e)

    # Cap at 50K chars to avoid blowing up the AI prompt
    return text[:50000]
