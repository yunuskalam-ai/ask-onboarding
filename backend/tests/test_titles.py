"""Readable document titles: from the heading or first line, stored once, backfilled."""

import pytest

from app.ingest.parsers import Page, title_of
from app.ingest.service import backfill_titles, ingest_file
from tests.conftest import fake_embed


@pytest.mark.parametrize(
    ("filename", "text", "title"),
    [
        ("leave.md", "# Paid Time Off and Leave Policy\n\nText.", "Paid Time Off and Leave Policy"),
        ("notes.md", "Intro line\n\n# Real Title\n", "Real Title"),  # the first '# ' heading
        ("faq-payroll.txt", "PAYROLL FAQ\n\nQ: ...", "Payroll FAQ"),
        ("guide.txt", "OFFICE GUIDE: LONDON AND MANCHESTER\n", "Office Guide: London and Manchester"),
        ("reset.txt", "IT HOW-TO: RESETTING YOUR OKTA PASSWORD", "IT How-To: Resetting your Okta Password"),
        (
            "conduct.pdf",
            "YK Labs Employee Handbook: Code of Conduct\n1. Our values",
            "YK Labs Employee Handbook: Code of Conduct",
        ),
        ("no-heading.md", "Just text, no heading.", "No heading"),
        ("empty_page.txt", "", "Empty page"),
        ("long.txt", "x" * 200, "Long"),  # a first line too long to be a title
    ],
)
def test_titles(filename, text, title):
    assert title_of(filename, [Page(None, text)]) == title


def test_processing_stores_the_title(db):
    ingest_file(db, "leave.md", b"# Leave Policy\n\nYou get 25 days.", embed=fake_embed)
    assert db.execute("SELECT title FROM documents").fetchone()["title"] == "Leave Policy"


def test_older_documents_get_their_title_once(db):
    ingest_file(db, "leave.md", b"# Leave Policy\n\nYou get 25 days.", embed=fake_embed)
    db.execute("UPDATE documents SET title = NULL")
    assert backfill_titles(db) == 1
    assert backfill_titles(db) == 0
    assert db.execute("SELECT title FROM documents").fetchone()["title"] == "Leave Policy"
