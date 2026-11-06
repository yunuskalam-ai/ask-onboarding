# Ask Onboarding

Ask Onboarding is a RAG assistant that answers new employees' questions from company documents. Every answer cites the exact passage it came from. When the documents don't cover a question, the app says "I don't know" and offers to open a help-desk ticket instead.

**Stack:** FastAPI · Postgres 16 + pgvector · fastembed (local embeddings) · Ollama with qwen2.5:3b (local LLM; Claude optional) · React + Vite + TypeScript · Docker Compose

Everything runs locally. No API key is needed.

> Status: work in progress. Upload, chat with clickable citations and the honest "not in the documents" answer work; help-desk tickets come next.

## Quick start

```bash
git clone https://github.com/yunuskalam-ai/ask-onboarding.git
cd ask-onboarding
docker compose up
```

This starts Postgres (with pgvector), Ollama, the API and the web app.

**Open http://localhost:8080.** Upload files on the Documents page, then ask questions on the Chat page.

**The first start takes a few minutes:** it downloads the Ollama image and the `qwen2.5:3b` model (about 1.9 GB). The API waits until the model is ready. Later starts take seconds.

The model runs on the CPU, so the first words of an answer take a few seconds. To use Claude instead, copy `.env.example` to `.env`, then set `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`.

- API docs (try the endpoints): http://localhost:8000/docs
- Upload a file: `curl -F "file=@sample_docs/faq-payroll.txt" localhost:8000/api/documents`
- See document status: `curl localhost:8000/api/documents`
- Ask a question (streams Server-Sent Events): `curl -N -H "Content-Type: application/json" -d '{"question": "Can I deploy on a Friday?"}' localhost:8000/api/chat`

## Running the tests

Tests need the database running (`docker compose up -d db`). They use a separate `ask_onboarding_test` database, so your data is not touched.

```bash
# inside Docker
docker compose exec api python -m pytest

# or locally
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt   # macOS/Linux: .venv/bin/pip
.venv/Scripts/python -m pytest
```

Frontend tests (stream parser and answer rendering):

```bash
cd frontend
npm ci
npm test
```

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
