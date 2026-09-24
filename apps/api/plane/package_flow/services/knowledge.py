# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Upload security and format classification on native FileAssets (FR-C05, FR-E04, PRD §15.1).

* MIME is sniffed from magic bytes and compared with the declared type.
* A scanner hook runs before any extraction/indexing: EICAR test signature,
  executables and script types are quarantined (configurable via settings
  ``PACKAGE_FLOW_UPLOAD_BLOCKED_MIME`` / ``PACKAGE_FLOW_UPLOAD_BLOCKED_EXT`` /
  ``PACKAGE_FLOW_UPLOAD_SCANNER`` = dotted path to ``fn(content, meta) -> (status, detail)``).
* Format support: ``native_edit`` / ``comment`` / ``preview`` / ``download``.
  Office documents (``.docx`` …) are never ``native_edit`` (FR-E04).
* Text extraction and search indexing happen only after a clean scan; no
  second file store — the native FileAsset keeps the bytes unchanged.
"""

import io
import logging
import os
import re
import zipfile

from django.conf import settings
from django.utils.module_loading import import_string

from plane.db.models import FileAsset, Issue

from ..errors import NotFound, ValidationFailed
from ..models import UploadRecord
from . import search

logger = logging.getLogger("plane.package_flow.knowledge")

MAX_SCAN_BYTES = 10 * 1024 * 1024
EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"

DEFAULT_BLOCKED_MIME = {
    "application/x-msdownload",
    "application/x-dosexec",
    "application/x-executable",
    "application/x-elf",
    "application/x-mach-binary",
    "application/x-sh",
    "text/x-shellscript",
    "application/x-bat",
    "application/javascript",
    "text/javascript",
    "application/x-msi",
    "application/java-archive",
    "text/html",
}
DEFAULT_BLOCKED_EXT = {
    ".exe", ".dll", ".msi", ".bat", ".cmd", ".com", ".scr", ".sh", ".ps1", ".vbs", ".js", ".jar",
    ".app", ".bin", ".elf", ".html", ".htm",
}

OFFICE_EXT = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
}
NATIVE_EDIT_MIME = {"text/plain", "text/markdown"}
COMMENT_MIME = {"image/png", "image/jpeg", "image/gif", "image/webp"}
PREVIEW_MIME = {"application/pdf", "image/svg+xml", *OFFICE_EXT.values(), "application/msword", "text/csv"}


def _ext(filename):
    return os.path.splitext((filename or "").lower())[1]


def sniff_mime(content: bytes, filename: str = "") -> str:
    """Detect MIME from magic bytes; the declared type is never trusted."""
    if content is None:
        return ""
    head = content[:512]
    ext = _ext(filename)
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"MZ"):
        return "application/x-msdownload"
    if head.startswith(b"\x7fELF"):
        return "application/x-executable"
    if head[:4] in (b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe"):
        return "application/x-mach-binary"
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return "application/msword"
    if head.startswith(b"PK\x03\x04"):
        try:
            names = set(zipfile.ZipFile(io.BytesIO(content)).namelist())
        except zipfile.BadZipFile:
            names = set()
        if "word/document.xml" in names:
            return OFFICE_EXT[".docx"]
        if "xl/workbook.xml" in names:
            return OFFICE_EXT[".xlsx"]
        if "ppt/presentation.xml" in names:
            return OFFICE_EXT[".pptx"]
        if "META-INF/MANIFEST.MF" in names:
            return "application/java-archive"
        return OFFICE_EXT.get(ext, "application/zip")
    if head.startswith(b"#!"):
        return "text/x-shellscript"
    try:
        text = head.decode("utf-8")
    except UnicodeDecodeError:
        return "application/octet-stream"
    stripped = text.lstrip().lower()
    if stripped.startswith("<svg") or (stripped.startswith("<?xml") and "<svg" in stripped):
        return "image/svg+xml"
    if stripped.startswith(("<!doctype html", "<html", "<script")):
        return "text/html"
    if stripped.startswith("<?xml"):
        return "application/xml"
    if ext == ".md":
        return "text/markdown"
    if ext == ".csv":
        return "text/csv"
    if ext == ".js":
        return "application/javascript"
    return "text/plain"


def _blocked_mime():
    return set(getattr(settings, "PACKAGE_FLOW_UPLOAD_BLOCKED_MIME", DEFAULT_BLOCKED_MIME))


def _blocked_ext():
    return set(getattr(settings, "PACKAGE_FLOW_UPLOAD_BLOCKED_EXT", DEFAULT_BLOCKED_EXT))


def builtin_scan(content: bytes, meta: dict):
    if EICAR in content:
        return UploadRecord.ScanStatus.QUARANTINED, "EICAR test signature detected"
    detected = meta.get("detected_mime", "")
    if detected in _blocked_mime():
        return UploadRecord.ScanStatus.QUARANTINED, f"Blocked content type {detected}"
    if _ext(meta.get("filename")) in _blocked_ext():
        return UploadRecord.ScanStatus.QUARANTINED, "Blocked file extension"
    declared = (meta.get("declared_mime") or "").lower()
    if declared and detected and declared.split("/")[0] in ("image", "text") and declared != detected:
        if detected.startswith("application/") and detected not in ("application/xml",):
            return UploadRecord.ScanStatus.QUARANTINED, f"Declared {declared} but content is {detected}"
    return UploadRecord.ScanStatus.CLEAN, "clean"


def scan(content, meta):
    if content is None:
        return UploadRecord.ScanStatus.PENDING, "content not yet available"
    status, detail = builtin_scan(content, meta)
    if status != UploadRecord.ScanStatus.CLEAN:
        return status, detail
    hook = getattr(settings, "PACKAGE_FLOW_UPLOAD_SCANNER", None)
    if hook:
        try:
            status, detail = import_string(hook)(content, meta)
        except Exception as exc:
            logger.exception("upload scanner hook failed")
            return UploadRecord.ScanStatus.FAILED, f"scanner error: {type(exc).__name__}"
    return status, detail


def format_support(detected_mime, filename=""):
    """FR-E04: an uploaded Office document is not natively editable."""
    ext = _ext(filename)
    if ext in OFFICE_EXT or detected_mime in OFFICE_EXT.values() or detected_mime == "application/msword":
        return UploadRecord.FormatSupport.PREVIEW
    if detected_mime in NATIVE_EDIT_MIME:
        return UploadRecord.FormatSupport.NATIVE_EDIT
    if detected_mime in COMMENT_MIME:
        return UploadRecord.FormatSupport.COMMENT
    if detected_mime in PREVIEW_MIME:
        return UploadRecord.FormatSupport.PREVIEW
    return UploadRecord.FormatSupport.DOWNLOAD


_XML_TAG = re.compile(r"<[^>]+>")


def extract_text(content, detected_mime, limit=200_000):
    """Only called after a clean scan."""
    try:
        if detected_mime in NATIVE_EDIT_MIME or detected_mime == "text/csv":
            return content.decode("utf-8", errors="replace")[:limit]
        if detected_mime == OFFICE_EXT[".docx"]:
            xml = zipfile.ZipFile(io.BytesIO(content)).read("word/document.xml").decode("utf-8", errors="replace")
            xml = xml.replace("</w:p>", "\n")
            return re.sub(r"[ \t]+", " ", _XML_TAG.sub("", xml)).strip()[:limit]
    except (KeyError, zipfile.BadZipFile, UnicodeDecodeError):
        return ""
    return ""


def read_asset_bytes(asset, limit=MAX_SCAN_BYTES):
    """Read the native asset from storage; ``None`` if not (yet) available."""
    try:
        with asset.asset.open("rb") as fh:
            return fh.read(limit)
    except Exception:
        return None


def register(user, project, asset_id, *, declared_mime="", filename="", issue_id=None, content=None):
    asset = FileAsset.objects.filter(
        id=asset_id, workspace_id=project.workspace_id, is_deleted=False
    ).first()
    if asset is None or (asset.project_id is not None and asset.project_id != project.id):
        raise NotFound("Asset not found")
    issue = None
    if issue_id:
        issue = Issue.objects.filter(id=issue_id, project=project).first()
        if issue is None:
            raise NotFound("Work item not found")
    filename = filename or (asset.attributes or {}).get("name") or os.path.basename(asset.asset.name or "")
    declared_mime = declared_mime or (asset.attributes or {}).get("type") or ""
    if content is None:
        content = read_asset_bytes(asset)
    if content is not None and len(content) > MAX_SCAN_BYTES:
        raise ValidationFailed("File too large to scan")
    detected = sniff_mime(content, filename) if content is not None else ""
    status, detail = scan(content, {"filename": filename, "declared_mime": declared_mime, "detected_mime": detected})

    record = UploadRecord.objects.filter(asset=asset).first() or UploadRecord(asset=asset)
    record.workspace_id = project.workspace_id
    record.project = project
    record.issue = issue or record.issue or (asset.issue if asset.issue_id else None)
    record.owner = record.owner or asset.created_by or user
    record.declared_mime = declared_mime[:255]
    record.detected_mime = detected[:255]
    record.scan_status = status
    record.scan_detail = str(detail)[:500]
    record.format_support = format_support(detected, filename)
    # Extraction and indexing only after a clean scan (FR-C05, PRD §15.1).
    if status == UploadRecord.ScanStatus.CLEAN:
        record.extracted_text = extract_text(content, detected)
    else:
        record.extracted_text = ""
    record.save()
    if status == UploadRecord.ScanStatus.CLEAN:
        search.index_document(
            workspace_id=record.workspace_id,
            object_type="upload",
            object_id=record.id,
            title=filename or "Upload",
            body=record.extracted_text,
            project_id=record.project_id,
            issue_id=record.issue_id,
        )
    else:
        search.remove_document("upload", record.id)
    return record


def serialize(record):
    return {
        "id": str(record.id),
        "asset_id": str(record.asset_id),
        "project_id": str(record.project_id) if record.project_id else None,
        "issue_id": str(record.issue_id) if record.issue_id else None,
        "owner_id": str(record.owner_id) if record.owner_id else None,
        "declared_mime": record.declared_mime,
        "detected_mime": record.detected_mime,
        "scan_status": record.scan_status,
        "scan_detail": record.scan_detail,
        "format_support": record.format_support,
        "has_extracted_text": bool(record.extracted_text),
        "updated_at": record.updated_at,
    }
