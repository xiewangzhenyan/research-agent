"""Real PDF fixtures for layout order and honest partial-text coverage."""

from collections import Counter

import pymupdf
import pytest

from app.services.knowledge_index import parse_with_report, split_blocks


def paragraph(label):
    return f"{label}. " + (
        "This synthetic paragraph checks document reading order and retains every word. "
        "Its content is generated solely for regression testing, not scientific evidence."
    )


def insert(page, rect, text):
    assert page.insert_textbox(pymupdf.Rect(*rect), text, fontsize=11) >= 0


def test_two_columns_with_full_width_sections_preserve_every_word():
    with pymupdf.open() as doc:
        page = doc.new_page(width=600, height=800)
        # Deliberately write the right column first, as many PDF streams do.
        for label, x, y in [
            ("RIGHT_TOP", 330, 100),
            ("RIGHT_BOTTOM", 330, 230),
            ("LEFT_TOP", 50, 100),
            ("LEFT_BOTTOM", 50, 230),
            ("SECOND_RIGHT", 330, 470),
            ("SECOND_LEFT", 50, 470),
        ]:
            insert(page, (x, y, x + 220, y + 120), paragraph(label))
        for label, y in [("HEADER", 40), ("SECTION", 410), ("FOOTER", 740)]:
            insert(
                page,
                (50, y, 550, y + 45),
                label + " across the full width of this synthetic document page.",
            )
        original = page.get_text()
        assert original.index("RIGHT_TOP") < original.index("LEFT_TOP")
        blocks, report = parse_with_report(doc.tobytes(), "columns.pdf")
    text = blocks[0]["text"]
    markers = [
        "HEADER",
        "LEFT_TOP",
        "LEFT_BOTTOM",
        "RIGHT_TOP",
        "RIGHT_BOTTOM",
        "SECTION",
        "SECOND_LEFT",
        "SECOND_RIGHT",
        "FOOTER",
    ]
    assert [text.index(m) for m in markers] == sorted(text.index(m) for m in markers)
    assert Counter(original.split()) == Counter(text.split())
    assert report["two_column_pages"] == [1]
    assert all(c["page"] == 1 for c in split_blocks(blocks))


def test_single_column_uses_geometry_instead_of_stream_order():
    with pymupdf.open() as doc:
        page = doc.new_page(width=600, height=800)
        insert(page, (50, 300, 550, 400), paragraph("BOTTOM"))
        insert(page, (50, 60, 550, 160), paragraph("TOP"))
        blocks, report = parse_with_report(doc.tobytes(), "single.pdf")
    assert blocks[0]["text"].index("TOP") < blocks[0]["text"].index("BOTTOM")
    assert report["two_column_pages"] == []


def test_short_side_by_side_labels_do_not_claim_two_column_layout():
    with pymupdf.open() as doc:
        page = doc.new_page(width=600, height=800)
        insert(page, (330, 80, 550, 120), "Right label")
        insert(page, (50, 80, 270, 120), "Left label")
        blocks, report = parse_with_report(doc.tobytes(), "labels.pdf")
    assert "Right label" in blocks[0]["text"] and "Left label" in blocks[0]["text"]
    assert report["two_column_pages"] == []


def test_partial_scan_with_page_number_and_blank_page_are_reported_separately():
    with pymupdf.open() as doc:
        insert(doc.new_page(), (50, 50, 500, 170), paragraph("TEXT"))
        doc.new_page()  # A blank page cannot be assumed to be a scan.
        page = doc.new_page()
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 3, 3))
        pixmap.clear_with(180)
        page.insert_image(page.rect, pixmap=pixmap, keep_proportion=False)
        page.insert_text((280, 800), "3")  # A page number is not full-page extraction.
        blocks, report = parse_with_report(doc.tobytes(), "mixed.pdf")
    assert report["total_pages"] == 3 and report["text_pages"] == 2
    assert report["empty_text_pages"] == [2]
    assert report["suspected_scan_pages"] == [3]
    assert {c["page"] for c in split_blocks(blocks)} == {1, 3}
    assert blocks[1]["text"] == ""


def test_image_only_document_still_fails_with_actionable_ocr_error():
    with pymupdf.open() as doc:
        doc.new_page()
        with pytest.raises(ValueError, match="OCR"):
            parse_with_report(doc.tobytes(), "empty.pdf")


def test_encrypted_document_has_specific_error():
    with pymupdf.open() as doc:
        doc.new_page().insert_text((50, 50), "Private fixture")
        raw = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="test-password")
    with pytest.raises(ValueError, match="加密"):
        parse_with_report(raw, "locked.pdf")


def test_non_pdf_has_no_invented_page_report():
    blocks, report = parse_with_report("实验资料".encode(), "notes.txt")
    assert report is None and blocks[0]["page"] is None


def test_short_centered_footer_stays_after_both_columns():
    with pymupdf.open() as doc:
        page = doc.new_page(width=600, height=800)
        insert(page, (330, 80, 550, 280), paragraph("RIGHT"))
        insert(page, (50, 80, 270, 280), paragraph("LEFT"))
        # Entire glyph is just left of the page midpoint.
        page.insert_text((294, 760), "7", fontsize=8)
        blocks, report = parse_with_report(doc.tobytes(), "footer.pdf")
    assert report["two_column_pages"] == [1]
    assert blocks[0]["text"].rstrip().endswith("7")


def test_complex_page_fallback_keeps_every_block_in_stream_order():
    from app.services.knowledge_pdf import _reading_order

    blocks = [(50, i, 550, i + 1, f"Block {i}") for i in range(2001, 0, -1)]
    ordered, columns = _reading_order(blocks, 600)
    assert not columns and ordered == blocks
