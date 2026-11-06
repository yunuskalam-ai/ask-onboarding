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
| `db/init.sql` | Enables the pgvector extension |

## Docs

These sections are written as the project progresses:

- Evaluation results
- Known limitations
- `ARCHITECTURE.md`: design, tradeoffs and scaling plan
- `AI_LOG.md`: how AI tools were used
