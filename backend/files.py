"""Turn an uploaded file into plain text for the intake (zero tokens).

Supported, each from an official export or download a student can make themselves:
- .zip  WhatsApp "Export chat" (the chat's .txt inside; media is ignored), with zip-bomb limits;
- .pdf  e.g. a Messages conversation printed to PDF on a Mac, or a saved posting;
- .eml  an email downloaded from Gmail / Outlook ("Download message"): sender name, date, subject and readable body;
- .ics  a calendar invite (booked calls); .csv (LinkedIn exports), .txt, .md, .html as text.
"""

from __future__ import annotations

import email
import io
import re
import zipfile
from email import policy

import safety

MAX_FILE_BYTES = 5_000_000  # one upload
MAX_ZIP_ENTRIES = 200
MAX_ZIP_UNCOMPRESSED = 30_000_000  # a WhatsApp export without media is a small text file
MAX_PDF_PAGES = 60
TEXT_TYPES = (".txt", ".md", ".csv", ".ics", ".html", ".htm")


class FileError(Exception):
    """A message for the student: why the file could not be read."""


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


def _zip_text(data: bytes) -> str:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise FileError("That ZIP file could not be opened.") from None
    infos = zf.infolist()
    if len(infos) > MAX_ZIP_ENTRIES or sum(i.file_size for i in infos) > MAX_ZIP_UNCOMPRESSED:
        raise FileError("That ZIP is too large. Export the chat again with 'Without media'.")
    texts = [i for i in infos if i.filename.lower().endswith(".txt") and not i.is_dir()]
    if not texts:
        raise FileError("No chat text (.txt) was found in that ZIP. Use WhatsApp's 'Export chat' and upload its ZIP.")
    texts.sort(key=lambda i: ("chat" not in i.filename.lower(), -i.file_size))
    return _decode(zf.read(texts[0]))


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = reader.pages[:MAX_PDF_PAGES]
        return "\n".join((p.extract_text() or "") for p in pages)
    except Exception:  # noqa: BLE001 - any malformed PDF
        raise FileError("That PDF could not be read. Copy the text and paste it instead.") from None


def _eml_text(data: bytes) -> str:
    msg = email.message_from_bytes(data, policy=policy.default)
    sender = msg.get("From", "")
    name = re.sub(r"<[^>]*>", "", str(sender)).strip().strip('"') or "unknown sender"
    body = msg.get_body(preferencelist=("plain", "html"))
    text = body.get_content() if body else ""
    if body is not None and body.get_content_type() == "text/html":
        text, _ = safety.visible_text(text)
    return f"From: {name}\nDate: {msg.get('Date', '')}\nSubject: {msg.get('Subject', '')}\n\n{text}"


def extract(filename: str, data: bytes) -> str:
    name = filename.lower()
    if len(data) > MAX_FILE_BYTES:
        raise FileError(f"That file is larger than {MAX_FILE_BYTES // 1_000_000} MB.")
    if name.endswith(".zip"):
        return _zip_text(data)
    if name.endswith(".pdf"):
        return _pdf_text(data)
    if name.endswith(".eml"):
        return _eml_text(data)
    if name.endswith(TEXT_TYPES):
        return _decode(data)
    raise FileError("Upload a .zip (WhatsApp export), .pdf, .eml, .ics, .csv, .txt or .html file.")
