# Ask Onboarding

Ask Onboarding is a RAG assistant that answers new employees' questions from company documents. Every answer cites the exact passage it came from. When the documents don't cover a question, the app says "I don't know" and offers to open a help-desk ticket instead.

**Stack:** FastAPI · Postgres 16 + pgvector · fastembed (local embeddings) · Claude (Anthropic API) · React + Vite + TypeScript · Docker Compose

> Status: work in progress (Phase 0, project setup).

## Quick start

```bash
git clone https://github.com/yunuskalam-ai/ask-onboarding.git
cd ask-onboarding
cp .env.example .env        # then set ANTHROPIC_API_KEY
docker compose up
```

Only the database runs at this stage. The API and web app are added in later phases.

## Project layout

| Path | Contents |
| --- | --- |
| `backend/app/` | FastAPI app: ingestion, retrieval, chat, tickets |
| `backend/tests/` | pytest tests |
| `frontend/` | React app: Upload, Chat and Tickets pages |
| `eval/` | 20-question evaluation set and scoring script |
| `sample_docs/` | Sample company documents, loaded on first start |
| `scripts/` | Helper scripts, such as the generator for the sample PDFs |
| `db/init.sql` | Enables the pgvector extension |

## Sample data

`sample_docs/` holds 18 documents for **Larkspur Labs**, a made-up 300-person software company. There are 12 Markdown files, 4 text files and 2 multi-page PDFs, covering the employee handbook, the engineering wiki, IT guides and office information. Every name, address and email in them is fictional (`*.example` domains).

Regenerate the PDFs with `pip install fpdf2==2.8.3 && python scripts/make_sample_pdfs.py`.

## Docs

These sections are written as the project progresses:

- Evaluation results
- Known limitations
- `ARCHITECTURE.md`: design, tradeoffs and scaling plan
- `AI_LOG.md`: how AI tools were used
