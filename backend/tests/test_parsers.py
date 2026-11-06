import pytest

from app.ingest.parsers import EmptyDocument, UnsupportedFileType, file_type, parse


def test_every_sample_doc_parses(sample_docs):
    files = sorted(p for p in sample_docs.iterdir() if p.is_file())
    assert len(files) == 18
    for path in files:
        pages = parse(path.name, path.read_bytes())
        assert pages, path.name
        assert any(page.text.strip() for page in pages), path.name


def test_pdf_keeps_one_page_per_pdf_page(sample_docs):
    path = sample_docs / "handbook-code-of-conduct.pdf"
    pages = parse(path.name, path.read_bytes())

    assert [page.number for page in pages] == [1, 2, 3, 4]
    # The gifts rule is on page 3, so a citation must point there.
    assert "£50" in pages[2].text
    assert "£50" not in pages[0].text


def test_markdown_is_one_page_kept_as_written(sample_docs):
    path = sample_docs / "handbook-pto-and-leave-policy.md"
    pages = parse(path.name, path.read_bytes())

    assert len(pages) == 1
    assert pages[0].number is None
    assert pages[0].text.startswith("# Paid Time Off and Leave Policy")


def test_windows_line_endings_and_bom_are_normalised():
    data = "﻿line one\r\nline two\r\n".encode("utf-8")
    [page] = parse("notes.txt", data)
    assert page.text == "line one\nline two\n"


def test_non_utf8_text_falls_back_to_cp1252():
    [page] = parse("old.txt", "Café costs £3".encode("cp1252"))
    assert page.text == "Café costs £3"


@pytest.mark.parametrize("name", ["report.docx", "image.png", "noextension"])
def test_unsupported_types_are_rejected(name):
    with pytest.raises(UnsupportedFileType):
        parse(name, b"anything")


def test_extension_check_ignores_case():
    assert file_type("Guide.PDF") == "pdf"
    assert file_type("notes.Markdown") == "md"


def test_whitespace_only_file_is_rejected():
    with pytest.raises(EmptyDocument):
        parse("blank.md", b"  \n\n\t ")


def test_corrupt_pdf_is_rejected():
    with pytest.raises(EmptyDocument):
        parse("broken.pdf", b"this is not a pdf")
