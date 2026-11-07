"""The text of a document the founder uploads, as passages a reader can find:
each with where it is ("page 3", "slide 2", "sheet Revenue, rows 2–41", a
section's heading) and its text, about a paragraph or two long.

The formats offices share: PDF, Word, PowerPoint and Excel (and their
OpenDocument kin), CSV, RTF, HTML, Markdown and plain text. The type is told
from the content, not the name. Only the text is kept, never the file, and a
file is read within limits: its size, how much an archive unpacks to, pages,
rows and characters. A scanned PDF has no text to read, and says so.
"""

import csv
import io
import re
import zipfile
from collections.abc import Iterable
from html.parser import HTMLParser

from defusedxml import ElementTree
from pydantic import BaseModel, Field

MAX_BYTES = 10_000_000
# What an archive (a .docx, .xlsx...) may unpack to, and how much more than its size.
MAX_UNPACKED = 80_000_000
MAX_RATIO = 100
MAX_PAGES = 400
MAX_ROWS = 5_000
MAX_CHARACTERS = 400_000
PASSAGE = 1_500
ROWS_A_PASSAGE = 40


class Passage(BaseModel):
    where: str = Field(description='Where it is in the document: "page 3", "slide 2", "sheet Revenue, rows 2–41".')
    text: str


class Extracted(BaseModel):
    kind: str = Field(description="PDF, Word, PowerPoint, Excel, CSV, OpenDocument text...")
    parts: str = Field(description='How long it is: "12 pages", "3 sheets", "8 slides".')
    passages: list[Passage]
    warnings: list[str] = Field(default_factory=list)

    @property
    def characters(self) -> int:
        return sum(len(passage.text) for passage in self.passages)


class Unreadable(ValueError):
    """The file cannot be read, and why, for the founder."""


# ---- Passages from blocks of text ----

def _tidy(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _passages(blocks: Iterable[tuple[str, str]]) -> list[Passage]:
    """Blocks of text, each with where it is, joined while they fit a passage
    and split where one is too long; at most MAX_CHARACTERS in all."""
    passages: list[Passage] = []
    total = 0
    for where, text in blocks:
        text = _tidy(text)
        if not text:
            continue
        while text and total < MAX_CHARACTERS:
            if len(text) <= PASSAGE:
                piece, text = text, ""
            else:
                cut = max(text.rfind("\n", 0, PASSAGE), text.rfind(". ", 0, PASSAGE) + 1)
                cut = cut if cut > PASSAGE // 2 else PASSAGE
                piece, text = text[:cut].strip(), text[cut:].strip()
            last = passages[-1] if passages else None
            if last and last.where == where and len(last.text) + len(piece) + 2 <= PASSAGE:
                last.text += "\n\n" + piece
            else:
                passages.append(Passage(where=where, text=piece))
            total += len(piece)
    return passages


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


# ---- Each format ----

def _pdf(data: bytes) -> Extracted:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise Unreadable("The PDF is protected by a password; save a copy without one.")
        pages = reader.pages
        count = len(pages)
        blocks = [(f"page {number}", page.extract_text() or "") for number, page in enumerate(pages[:MAX_PAGES], start=1)]
    except (PdfReadError, ValueError, KeyError, TypeError) as error:
        if isinstance(error, Unreadable):
            raise
        raise Unreadable("The PDF could not be read; it may be damaged.") from error
    passages = _passages(blocks)
    warnings = [f"Only the first {MAX_PAGES} of {count} pages were read."] if count > MAX_PAGES else []
    if not passages:
        raise Unreadable("The PDF has no text to read: it may be scanned images. Upload a copy with text in it.")
    return Extracted(kind="PDF", parts=_plural(count, "page"), passages=passages, warnings=warnings)


def _docx(data: bytes) -> Extracted:
    import docx

    document = docx.Document(io.BytesIO(data))
    blocks: list[tuple[str, str]] = []
    heading = "the start"
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        style = paragraph.style.name if paragraph.style is not None else None
        if (style or "").lower().startswith(("heading", "title")):
            heading = text[:80]
        blocks.append((f"section “{heading}”", text))
    for number, table in enumerate(document.tables, start=1):
        rows = [" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows[:MAX_ROWS]]
        blocks.append((f"table {number}", "\n".join(rows)))
    count = len([b for b in blocks if b[0].startswith("section")])
    return Extracted(kind="Word", parts=f"{_plural(count, 'paragraph')}, {_plural(len(document.tables), 'table')}",
                     passages=_passages(blocks))


def _pptx(data: bytes) -> Extracted:
    from pptx import Presentation
    from pptx.shapes.autoshape import Shape
    from pptx.shapes.graphfrm import GraphicFrame

    deck = Presentation(io.BytesIO(data))
    blocks = []
    for number, slide in enumerate(deck.slides, start=1):
        texts = [shape.text_frame.text for shape in slide.shapes if isinstance(shape, Shape) and shape.has_text_frame]
        for shape in slide.shapes:
            if isinstance(shape, GraphicFrame) and shape.has_table:
                texts.append("\n".join(" | ".join(cell.text for cell in row.cells) for row in shape.table.rows))
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                texts.append(f"Notes: {notes}")
        blocks.append((f"slide {number}", "\n".join(texts)))
    return Extracted(kind="PowerPoint", parts=_plural(len(deck.slides), "slide"), passages=_passages(blocks))


def _rows(name: str, rows: Iterable[list[str]]) -> tuple[list[tuple[str, str]], int]:
    """Rows of a table, a passage of ROWS_A_PASSAGE at a time, as "a | b | c"."""
    blocks, chunk, first, count = [], [], 1, 0
    for count, row in enumerate(rows, start=1):
        if count > MAX_ROWS:
            count -= 1
            break
        chunk.append(" | ".join(cell for cell in row).rstrip(" |"))
        if len(chunk) == ROWS_A_PASSAGE:
            blocks.append((f"{name}rows {first}–{count}", "\n".join(chunk)))
            chunk, first = [], count + 1
    if chunk:
        blocks.append((f"{name}rows {first}–{count}" if count > first else f"{name}row {first}", "\n".join(chunk)))
    return blocks, count


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _xlsx(data: bytes) -> Extracted:
    from openpyxl import load_workbook

    book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    blocks, warnings = [], []
    for sheet in book.worksheets:
        rows = ([_cell(value) for value in row] for row in sheet.iter_rows(values_only=True))
        found, count = _rows(f"sheet {sheet.title}, ", (row for row in rows if any(row)))
        blocks += found
        if count >= MAX_ROWS:
            warnings.append(f"Only the first {MAX_ROWS} rows of sheet {sheet.title} were read.")
    sheets = len(book.worksheets)
    book.close()
    return Extracted(kind="Excel", parts=_plural(sheets, "sheet"), passages=_passages(blocks), warnings=warnings)


def _csv(text: str) -> Extracted:
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = [row for row in csv.reader(io.StringIO(text), dialect) if any(cell.strip() for cell in row)]
    blocks, count = _rows("", ([cell.strip() for cell in row] for row in rows))
    return Extracted(kind="CSV", parts=_plural(count, "row"), passages=_passages(blocks))


ODF = {
    "application/vnd.oasis.opendocument.text": "OpenDocument text",
    "application/vnd.oasis.opendocument.spreadsheet": "OpenDocument spreadsheet",
    "application/vnd.oasis.opendocument.presentation": "OpenDocument presentation",
}
_TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
_TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
_DRAW = "{urn:oasis:names:tc:opendocument:xmlns:drawing:1.0}"


def _odf(archive: zipfile.ZipFile, kind: str) -> Extracted:
    root = ElementTree.fromstring(archive.read("content.xml"))

    def text_of(element) -> str:
        return "".join(element.itertext()).strip()

    if kind.endswith("spreadsheet"):
        blocks, sheets = [], root.iter(f"{_TABLE}table")
        count = 0
        for sheet in sheets:
            count += 1
            rows = ([text_of(cell) for cell in row.iter(f"{_TABLE}table-cell")] for row in sheet.iter(f"{_TABLE}table-row"))
            found, _ = _rows(f"sheet {sheet.get(f'{_TABLE}name')}, ", (row for row in rows if any(row)))
            blocks += found
        return Extracted(kind=kind, parts=_plural(count, "sheet"), passages=_passages(blocks))
    if kind.endswith("presentation"):
        pages = list(root.iter(f"{_DRAW}page"))
        blocks = [(f"slide {n}", "\n".join(text_of(p) for p in page.iter(f"{_TEXT}p"))) for n, page in enumerate(pages, start=1)]
        return Extracted(kind=kind, parts=_plural(len(pages), "slide"), passages=_passages(blocks))
    blocks, heading = [], "the start"
    for element in root.iter():
        if element.tag == f"{_TEXT}h":
            heading = text_of(element)[:80] or heading
        if element.tag in (f"{_TEXT}h", f"{_TEXT}p") and text_of(element):
            blocks.append((f"section “{heading}”", text_of(element)))
    return Extracted(kind=kind, parts=_plural(len(blocks), "paragraph"), passages=_passages(blocks))


class _HtmlText(HTMLParser):
    SKIP = {"script", "style", "noscript", "template", "svg"}
    BLOCKS = {"p", "div", "li", "br", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "table"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skipping = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skipping += 1
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skipping:
            self.skipping -= 1
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skipping:
            self.parts.append(data)


def _plain(text: str, kind: str) -> Extracted:
    """Text, Markdown or HTML: sections by heading where there are any, else parts."""
    if kind == "HTML":
        parser = _HtmlText()
        parser.feed(text)
        text = "".join(parser.parts)
    blocks, heading, number = [], None, 0
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        number += 1
        match = re.match(r"#{1,6}\s+(.+)", paragraph)
        if match:
            heading = match.group(1).strip()[:80]
        blocks.append((f"section “{heading}”" if heading else f"part {1 + (number - 1) // 4}", paragraph))
    return Extracted(kind=kind, parts=_plural(number, "paragraph"), passages=_passages(blocks))


def _rtf(text: str) -> Extracted:
    from striprtf.striprtf import rtf_to_text

    found = _plain(rtf_to_text(text, errors="ignore"), "RTF")
    return found


# ---- Telling the kind from the content ----

def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16") if data[:2] in (b"\xff\xfe", b"\xfe\xff") else ("utf-8-sig",):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    try:
        return data.decode("cp1252")
    except UnicodeDecodeError as error:
        raise Unreadable("This is not a kind of file the team can read.") from error


def _binary(data: bytes) -> bool:
    """Whether the start of the file is mostly not text: an image, a program."""
    head = data[:2048]
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return False  # UTF-16 text has a zero byte in every other place
    controls = sum(1 for byte in head if byte < 9 or 13 < byte < 32 or byte == 127)
    return controls > len(head) * 0.05


def _archive(data: bytes) -> zipfile.ZipFile:
    archive = zipfile.ZipFile(io.BytesIO(data))
    unpacked = sum(info.file_size for info in archive.infolist())
    if unpacked > MAX_UNPACKED or unpacked > MAX_RATIO * max(len(data), 1):
        raise Unreadable("The file unpacks to far more than its size, so it was not opened.")
    return archive


def extract(name: str, data: bytes) -> Extracted:
    """The passages of an uploaded file, or Unreadable with the reason."""
    if not data:
        raise Unreadable("The file is empty.")
    if len(data) > MAX_BYTES:
        raise Unreadable(f"The file is larger than {MAX_BYTES // 1_000_000} MB.")
    extension = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    try:
        if data.startswith(b"%PDF"):
            return _pdf(data)
        if data.startswith(b"\xd0\xcf\x11\xe0"):
            raise Unreadable("This is an older Office file (.doc, .xls or .ppt). Save it as .docx, .xlsx or .pptx and upload that.")
        if data.startswith(b"PK"):
            archive = _archive(data)
            names = set(archive.namelist())
            if "word/document.xml" in names:
                return _docx(data)
            if "ppt/presentation.xml" in names:
                return _pptx(data)
            if "xl/workbook.xml" in names:
                return _xlsx(data)
            if "mimetype" in names and archive.read("mimetype").decode("ascii", "ignore").strip() in ODF:
                return _odf(archive, ODF[archive.read("mimetype").decode("ascii").strip()])
            raise Unreadable("This archive is not a document the team can read.")
        if _binary(data):
            raise Unreadable("This is not a kind of file the team can read: images and other binary files have no text.")
        text = _decode(data)
        if text.lstrip().startswith("{\\rtf"):
            return _rtf(text)
        if extension == "csv" or (extension == "tsv"):
            return _csv(text)
        if extension in ("html", "htm") or re.match(r"\s*(<!doctype html|<html)", text, re.IGNORECASE):
            return _plain(text, "HTML")
        return _plain(text, "Markdown" if extension in ("md", "markdown") else "Text")
    except Unreadable:
        raise
    except (zipfile.BadZipFile, KeyError, ValueError, ElementTree.ParseError, OSError) as error:
        raise Unreadable(f"The file could not be read; it may be damaged ({type(error).__name__}).") from error
