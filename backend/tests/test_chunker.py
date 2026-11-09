from itertools import pairwise

import pytest

from app.ingest.chunker import chunk_pages, chunk_spans
from app.ingest.parsers import Page, parse

SIZE, OVERLAP = 800, 100


def _all_sample_pages(sample_docs):
    for path in sorted(sample_docs.iterdir()):
        yield path.name, parse(path.name, path.read_bytes())


def test_offsets_point_at_the_exact_chunk_text(sample_docs):
    for name, pages in _all_sample_pages(sample_docs):
        texts = {page.number: page.text for page in pages}
        for chunk in chunk_pages(pages, SIZE, OVERLAP):
            assert texts[chunk.page][chunk.start_char : chunk.end_char] == chunk.text, name


def test_chunks_respect_the_size_limit(sample_docs):
    for name, pages in _all_sample_pages(sample_docs):
        for chunk in chunk_pages(pages, SIZE, OVERLAP):
            assert 0 < len(chunk.text) <= SIZE, name


def test_every_word_of_every_page_is_in_some_chunk(sample_docs):
    for name, pages in _all_sample_pages(sample_docs):
        chunks = chunk_pages(pages, SIZE, OVERLAP)
        for page in pages:
            covered = [False] * len(page.text)
            for chunk in chunks:
                if chunk.page == page.number:
                    for i in range(chunk.start_char, chunk.end_char):
                        covered[i] = True
            missed = [c for c, hit in zip(page.text, covered, strict=True) if not hit and not c.isspace()]
            assert missed == [], name


def test_neighbouring_chunks_overlap():
    text = " ".join(f"word{i}" for i in range(400))  # about 2,700 characters
    spans = chunk_spans(text, SIZE, OVERLAP)

    assert len(spans) >= 3
    for (_, prev_end), (next_start, _) in pairwise(spans):
        assert next_start < prev_end  # they share text
        assert prev_end - next_start <= OVERLAP


def test_chunks_prefer_paragraph_breaks():
    first = "A" * 500 + "."
    second = "B" * 500 + "."
    spans = chunk_spans(f"{first}\n\n{second}", SIZE, OVERLAP)

    assert spans[0] == (0, len(first))  # ends at the paragraph, not mid-way through B


def test_chunks_do_not_start_mid_word():
    text = " ".join(f"word{i}" for i in range(400))
    for start, end in chunk_spans(text, SIZE, OVERLAP)[1:]:
        assert text[start - 1] == " "
        assert text[start:end].startswith("word")


def test_chunks_never_cross_pdf_pages(sample_docs):
    path = sample_docs / "handbook-code-of-conduct.pdf"
    chunks = chunk_pages(parse(path.name, path.read_bytes()), SIZE, OVERLAP)

    assert {chunk.page for chunk in chunks} == {1, 2, 3, 4}
    gift_chunks = [c for c in chunks if "£50" in c.text]
    assert gift_chunks and all(c.page == 3 for c in gift_chunks)


def test_chunk_index_runs_across_the_whole_document():
    pages = [Page(1, "first page " * 100), Page(2, "second page " * 100)]
    chunks = chunk_pages(pages, SIZE, OVERLAP)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_short_text_is_one_chunk_and_blank_text_is_none():
    assert chunk_spans("  Hello there.  ", SIZE, OVERLAP) == [(2, 14)]
    assert chunk_spans(" \n\n ", SIZE, OVERLAP) == []


def test_a_word_longer_than_size_is_cut():
    spans = chunk_spans("x" * 2000, SIZE, OVERLAP)
    assert spans[0] == (0, SIZE)


@pytest.mark.parametrize("size, overlap", [(0, 0), (800, 400), (800, -1)])
def test_bad_settings_are_rejected(size, overlap):
    with pytest.raises(ValueError):
        chunk_spans("some text", size, overlap)
