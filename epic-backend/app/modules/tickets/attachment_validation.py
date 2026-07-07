"""
Attachment validation helpers: extension allowlist, best-effort magic-byte sniffing,
and safe filename handling for the Content-Disposition header.

Kept dependency-free (no python-magic) — the signature table below covers the file
types in ATTACHMENT_ALLOWED_EXTENSIONS. Extend it if you widen the allowlist.
"""
import re

# (extension-agnostic) magic-byte signatures for common allowed types.
_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"%PDF-", "application/pdf"),
    (b"PK\x03\x04", "application/zip"),  # also docx/xlsx/pptx (zip containers)
]


def sniff_mime(data: bytes) -> str | None:
    """Best-effort magic-byte sniff. Returns None for types we don't fingerprint (e.g. text/csv)."""
    for sig, mime in _SIGNATURES:
        if data.startswith(sig):
            return mime
    return None


# Extensions we can fingerprint, and the sniffed mime type(s) we require for each.
# Anything not in this map (e.g. .txt, .log, .csv) can't be fingerprinted by magic bytes,
# so we fall back to trusting the extension for those — they can't execute in a browser,
# which is the main risk this check guards against.
_FINGERPRINTABLE_EXTENSIONS: dict[str, set[str]] = {
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".gif": {"image/gif"},
    ".pdf": {"application/pdf"},
    ".docx": {"application/zip"},
    ".xlsx": {"application/zip"},
    ".pptx": {"application/zip"},
    ".zip": {"application/zip"},
}


def validate_attachment(file_name: str, declared_content_type: str | None, data: bytes,
                         allowed_extensions: set[str], allowed_mime_types: set[str]) -> None:
    """Raises ValueError with a user-facing message if the attachment is not permitted."""
    ext = ("." + file_name.rsplit(".", 1)[-1].lower()) if "." in file_name else ""
    if ext not in allowed_extensions:
        raise ValueError(f"Attachments with extension '{ext or '(none)'}' are not permitted")

    expected = _FINGERPRINTABLE_EXTENSIONS.get(ext)
    if expected is not None:
        sniffed = sniff_mime(data)
        if sniffed not in expected:
            raise ValueError("File content does not match a permitted attachment type")
    # else: extension isn't fingerprintable (txt/log/csv) — trust it, since it can't execute
    # in-browser regardless of its real content.


_UNSAFE_FILENAME_CHARS = re.compile(r'[\r\n"\\]')


def safe_download_filename(file_name: str) -> str:
    """Strip characters that could break out of the Content-Disposition header value."""
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", file_name)
    return cleaned or "attachment"