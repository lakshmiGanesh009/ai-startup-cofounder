"""Tests for reading the documents the founder uploads (extract.py): each
format the offices share, made here with the same libraries, read into
passages that say where they are; and the files refused, with why."""

import io
import zipfile

import docx
import pytest
from fpdf import FPDF
from openpyxl import Workbook
from pptx import Presentation
from pptx.util import Inches

from extract import MAX_BYTES, PASSAGE, Unreadable, extract


def _pdf(pages: list[str], encrypt: bool = False) -> bytes:
    pdf = FPDF()
    pdf.set_font("helvetica", size=11)
    for text in pages:
        pdf.add_page()
        if text:
            pdf.multi_cell(0, 6, text)
        else:
            pdf.rect(20, 20, 50, 50, style="F")  # a page with no text, as a scan has
    if encrypt:
        pdf.set_encryption(owner_password="owner", user_password="secret")
    return bytes(pdf.output())


def _where(found) -> list[str]:
    return [passage.where for passage in found.passages]


def test_a_pdf_is_read_page_by_page():
    found = extract("plan.pdf", _pdf(["Clinics pay $149 a month.", "Churn is 3% a month."]))
    assert (found.kind, found.parts) == ("PDF", "2 pages")
    assert [(p.where, p.text) for p in found.passages] == [
        ("page 1", "Clinics pay $149 a month."), ("page 2", "Churn is 3% a month.")]


def test_a_scanned_or_locked_pdf_says_why_it_cannot_be_read():
    with pytest.raises(Unreadable, match="scanned"):
        extract("scan.pdf", _pdf(["", ""]))
    with pytest.raises(Unreadable, match="password"):
        extract("locked.pdf", _pdf(["Secret plans."], encrypt=True))


def test_a_word_document_is_read_by_section_and_table():
    document = docx.Document()
    document.add_heading("Pricing", level=1)
    document.add_paragraph("A flat $149 a month per clinic.")
    document.add_heading("Risks", level=1)
    document.add_paragraph("HIPAA applies once notes hold PHI.")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Item", "Cost"
    table.cell(1, 0).text, table.cell(1, 1).text = "Legal", "$3,000"
    buffer = io.BytesIO()
    document.save(buffer)

    found = extract("memo.docx", buffer.getvalue())
    assert found.kind == "Word"
    assert _where(found) == ["section “Pricing”", "section “Risks”", "table 1"]
    assert "A flat $149 a month per clinic." in found.passages[0].text
    assert found.passages[2].text == "Item | Cost\nLegal | $3,000"


def test_slides_and_their_notes_are_read_one_slide_at_a_time():
    deck = Presentation()
    for title, notes in (("The problem", "Clinics lose follow-ups."), ("The plan", "")):
        slide = deck.slides.add_slide(deck.slide_layouts[5])
        slide.shapes.title.text = title
        if notes:
            slide.notes_slide.notes_text_frame.text = notes
    box = deck.slides[1].shapes.add_textbox(Inches(1), Inches(2), Inches(4), Inches(1))
    box.text_frame.text = "Pilot with 5 clinics."
    buffer = io.BytesIO()
    deck.save(buffer)

    found = extract("deck.pptx", buffer.getvalue())
    assert (found.kind, found.parts) == ("PowerPoint", "2 slides")
    assert [(p.where, p.text) for p in found.passages] == [
        ("slide 1", "The problem\nNotes: Clinics lose follow-ups."), ("slide 2", "The plan\nPilot with 5 clinics.")]


def test_a_spreadsheet_is_read_in_rows_by_sheet():
    book = Workbook()
    sheet = book.active
    sheet.title = "Revenue"
    sheet.append(["Year", "Customers", "Revenue"])
    for year in range(1, 46):
        sheet.append([year, year * 10, year * 1490.0])
    book.create_sheet("Costs").append(["Hosting", 600])
    buffer = io.BytesIO()
    book.save(buffer)

    found = extract("model.xlsx", buffer.getvalue())
    assert (found.kind, found.parts) == ("Excel", "2 sheets")
    assert _where(found) == ["sheet Revenue, rows 1–40", "sheet Revenue, rows 41–46", "sheet Costs, row 1"]
    assert found.passages[0].text.startswith("Year | Customers | Revenue\n1 | 10 | 1490")


def test_csv_html_markdown_text_and_rtf():
    csv = extract("data.csv", b"name;price\nBasic;149\nPro;299\n")
    assert (csv.kind, csv.passages[0].text) == ("CSV", "name | price\nBasic | 149\nPro | 299")

    html = extract("page.html", b"<html><head><style>p{}</style><script>alert(1)</script></head>"
                                b"<body><h1>Plans</h1><p>Basic is $149.</p></body></html>")
    assert html.kind == "HTML" and "Basic is $149." in html.passages[0].text and "alert" not in html.passages[0].text

    markdown = extract("notes.md", "# Market\n\n12,000 clinics.\n\n# Price\n\n$149 a month.".encode())
    assert [(p.where, p.text) for p in markdown.passages] == [
        ("section “Market”", "# Market\n\n12,000 clinics."), ("section “Price”", "# Price\n\n$149 a month.")]

    text = extract("notes.txt", "Plain notes, with “quotes” and €.".encode("utf-16"))
    assert (text.kind, text.passages[0].text) == ("Text", "Plain notes, with “quotes” and €.")

    rtf = extract("letter.rtf", rb"{\rtf1\ansi Dear founder, {\b the pilot} starts in May.}")
    assert rtf.kind == "RTF" and "the pilot starts in May." in rtf.passages[0].text


def test_an_opendocument_text_is_read_by_section():
    content = (
        '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:text>'
        "<text:h>Goals</text:h><text:p>Ten clinics by June.</text:p></office:text></office:body></office:document-content>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        archive.writestr("content.xml", content)
    found = extract("plan.odt", buffer.getvalue())
    assert found.kind == "OpenDocument text"
    assert [(p.where, p.text) for p in found.passages] == [("section “Goals”", "Goals\n\nTen clinics by June.")]


def test_long_text_is_split_into_passages_that_fit():
    paragraph = "A sentence about the clinic market. " * 30
    found = extract("long.txt", "\n\n".join([paragraph] * 6).encode())
    assert len(found.passages) > 3 and all(len(p.text) <= PASSAGE for p in found.passages)


@pytest.mark.parametrize(
    ("data", "words"),
    [
        (b"", "empty"),
        (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100, "older Office file"),
        (b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 4, "binary"),
        (b"PK\x03\x04 not really a zip", "damaged"),
        (b"x" * (MAX_BYTES + 1), "larger than"),
    ],
)
def test_files_that_cannot_be_read_say_why(data, words):
    with pytest.raises(Unreadable, match=words):
        extract("file.bin", data)


def test_an_archive_that_unpacks_to_far_more_is_not_opened():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", b"0" * 60_000_000)
    with pytest.raises(Unreadable, match="unpacks to far more"):
        extract("bomb.docx", buffer.getvalue())


def test_xml_with_entities_is_refused():
    content = ('<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
               '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0">&b;</office:document-content>')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        archive.writestr("content.xml", content)
    with pytest.raises(Unreadable):
        extract("entities.odt", buffer.getvalue())
