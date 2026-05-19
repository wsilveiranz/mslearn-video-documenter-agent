"""Fixtures for document converter integration tests.

These create real document files for testing MarkItDown conversion end-to-end.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def sample_docx(tmp_path_factory: pytest.TempPathFactory) -> Path:
    docx = pytest.importorskip("docx")

    tmp_path = tmp_path_factory.mktemp("docx")
    path = tmp_path / "test_document.docx"

    doc = docx.Document()
    doc.add_heading("Integration Test Document", level=1)
    doc.add_paragraph("This paragraph contains unique verification text alpha-bravo-charlie.")

    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Header1"
    table.cell(0, 1).text = "Header2"
    table.cell(1, 0).text = "CellA"
    table.cell(1, 1).text = "CellB"

    doc.add_paragraph("Bullet item delta-echo-foxtrot", style="List Bullet")

    doc.save(str(path))
    return path


@pytest.fixture(scope="session")
def sample_pdf(tmp_path_factory: pytest.TempPathFactory) -> Path:
    fpdf = pytest.importorskip("fpdf")

    tmp_path = tmp_path_factory.mktemp("pdf")
    path = tmp_path / "test_document.pdf"

    pdf = fpdf.FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", style="B", size=16)
    pdf.cell(0, 10, "PDF Test Document", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10, "This PDF contains verification text golf-hotel-india for testing.")
    pdf.output(str(path))

    return path


@pytest.fixture(scope="session")
def sample_pptx(tmp_path_factory: pytest.TempPathFactory) -> Path:
    pptx = pytest.importorskip("pptx")

    tmp_path = tmp_path_factory.mktemp("pptx")
    path = tmp_path / "test_presentation.pptx"

    prs = pptx.Presentation()

    title_slide_layout = prs.slide_layouts[0]
    slide1 = prs.slides.add_slide(title_slide_layout)
    slide1.shapes.title.text = "Presentation Test"
    slide1.placeholders[1].text = "juliet-kilo-lima verification"

    content_slide_layout = prs.slide_layouts[1]
    slide2 = prs.slides.add_slide(content_slide_layout)
    slide2.shapes.title.text = "Content Slide"
    slide2.placeholders[1].text = "This slide has content mike-november-oscar."

    prs.save(str(path))
    return path
