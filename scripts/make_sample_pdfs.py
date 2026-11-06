"""Generate the two sample PDF documents in sample_docs/.

The PDFs are committed, so you only need this script to change them.
Each section is placed on its own page on purpose: the app cites PDFs by
page number, and multi-page files let us test that.

Usage:
    pip install fpdf2==2.8.3
    python scripts/make_sample_pdfs.py
"""

from pathlib import Path

from fpdf import FPDF

OUT_DIR = Path(__file__).resolve().parent.parent / "sample_docs"

# Each document is a title plus a list of pages.
# Each page is (heading, [paragraphs]). Built-in PDF fonts only support
# Latin-1, so the text avoids curly quotes and long dashes.
DOCUMENTS = {
    "handbook-code-of-conduct.pdf": (
        "Larkspur Labs Employee Handbook: Code of Conduct",
        [
            (
                "1. Our values",
                [
                    "This Code of Conduct applies to everyone who works at or for Larkspur Labs: "
                    "employees, contractors and interns. Read it in your first week and confirm "
                    "in PeopleHub that you have read it.",
                    "Our four values are: Customers first, Own the outcome, Be straightforward, "
                    "and Leave it better. We use them in hiring, in performance reviews and when "
                    "we make hard decisions.",
                    "The People team reviews this Code every year. The current version was "
                    "approved by the leadership team in August 2026.",
                ],
            ),
            (
                "2. Respect, harassment and discrimination",
                [
                    "We do not tolerate harassment, bullying or discrimination of any kind, "
                    "including on the basis of age, disability, gender identity, marriage, "
                    "pregnancy, race, religion, sex or sexual orientation.",
                    "This applies everywhere work happens: in the office, on video calls, on "
                    "Slack, at client sites and at company events, including social events "
                    "after work.",
                    "If you experience or see harassment, tell your manager, the People team "
                    "(people@larkspur.example) or use the confidential Ethics Line described in "
                    "section 4. Complaints are investigated within 10 working days.",
                ],
            ),
            (
                "3. Conflicts of interest, gifts and outside work",
                [
                    "A conflict of interest is any situation where your personal interests could "
                    "affect your decisions at work, for example hiring a relative or buying from "
                    "a supplier owned by a friend. Declare any possible conflict to your manager "
                    "and the People team in writing.",
                    "Gifts and hospitality: you may accept small gifts worth up to £50. "
                    "Any gift or hospitality worth more than £50 must be recorded in the "
                    "Gift Register in Notion within 5 working days. Never accept cash or gifts "
                    "from a supplier during a tender.",
                    "Outside work: you may take on a second job or side project if it does not "
                    "compete with Larkspur Labs, use company time or equipment, or affect your "
                    "work. Ask your manager for approval in writing first.",
                ],
            ),
            (
                "4. Raising concerns and disciplinary process",
                [
                    "Speak up if you think something is wrong: fraud, a safety risk, a data "
                    "breach or a breach of this Code. Raise it with your manager, the People "
                    "team or the Legal team.",
                    "Ethics Line: if you prefer to stay anonymous, use the Ethics Line, an "
                    "independent service run by an outside company. It is open 24 hours a day "
                    "by phone or web form; the details are pinned in #people-help. Larkspur Labs "
                    "will never punish anyone for raising a concern in good faith.",
                    "Breaches of this Code are handled through the disciplinary process. The "
                    "steps are an investigation, a disciplinary meeting where you may bring a "
                    "colleague or union representative, a written outcome within 5 working days, "
                    "and the right to appeal within 10 working days. Serious breaches, such as "
                    "theft or violence, can lead to dismissal without notice.",
                ],
            ),
        ],
    ),
    "handbook-performance-reviews.pdf": (
        "Larkspur Labs: Performance Reviews and Promotions",
        [
            (
                "1. The review cycle",
                [
                    "Larkspur Labs runs performance reviews twice a year, in April and in "
                    "October. Each cycle takes about four weeks from self-review to the final "
                    "conversation with your manager.",
                    "Reviews happen in PeopleHub. Employees still in probation take part in "
                    "their 90-day check-in instead of the review cycle.",
                    "The steps are: 1) self-review (1 week), 2) peer feedback (1 week), "
                    "3) manager review and calibration (1 week), 4) a review conversation "
                    "with your manager (1 week).",
                ],
            ),
            (
                "2. Feedback and ratings",
                [
                    "Peer feedback: you choose 3 peers to give feedback, and your manager can add "
                    "one more. Peer feedback is shared with you without names.",
                    "Ratings use four levels: Exceeds expectations, Meets expectations, "
                    "Partially meets expectations, and Does not meet expectations.",
                    "Calibration: managers in each department meet to compare ratings, so that "
                    "the same performance gets the same rating across teams. Your manager tells "
                    "you your final rating in your review conversation.",
                    "If you get Partially meets or Does not meet expectations, you and your "
                    "manager agree a written support plan with goals for the next 3 months.",
                ],
            ),
            (
                "3. Promotions and pay reviews",
                [
                    "Promotions are decided in the October cycle only. Your manager nominates "
                    "you with a short written case based on the career framework in Notion. "
                    "Promotions take effect on 1 November.",
                    "Salary reviews happen once a year, in the April cycle. Pay increases "
                    "take effect from 1 May and appear in your May payslip.",
                    "Pay increases depend on your rating, your position in the salary band for "
                    "your level and the company budget for that year. Salary bands for every "
                    "level are published in PeopleHub.",
                    "If you disagree with your review outcome, raise it with your manager first, "
                    "then with your department head or the People team within 10 working days.",
                ],
            ),
        ],
    ),
}


class HandbookPDF(FPDF):
    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", size=9)
        self.cell(0, 10, f"Page {self.page_no()} of {{nb}}", align="C")


def build(filename: str, title: str, pages: list[tuple[str, list[str]]]) -> None:
    pdf = HandbookPDF()
    pdf.set_title(title)
    pdf.set_author("Larkspur Labs People team")
    pdf.set_margins(20, 20, 20)
    for i, (heading, paragraphs) in enumerate(pages):
        pdf.add_page()
        if i == 0:
            pdf.set_font("Helvetica", style="B", size=16)
            pdf.multi_cell(0, 9, title)
            pdf.ln(4)
        pdf.set_font("Helvetica", style="B", size=13)
        pdf.multi_cell(0, 8, heading)
        pdf.ln(2)
        pdf.set_font("Helvetica", size=11)
        for paragraph in paragraphs:
            pdf.multi_cell(0, 6, paragraph)
            pdf.ln(3)
    pdf.output(str(OUT_DIR / filename))
    print(f"wrote {filename} ({len(pages)} pages)")


if __name__ == "__main__":
    for name, (doc_title, doc_pages) in DOCUMENTS.items():
        build(name, doc_title, doc_pages)
