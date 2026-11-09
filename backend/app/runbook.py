"""What an admin should do about each kind of system alert.

Every alert has a dedupe key (see notifications.alert_admins). The key's kind
picks a runbook: what the alert means for people using the app, the likely
causes, the steps to fix it (with the exact commands), and which live checks
show whether it has recovered. Commands are for the Docker Compose stack; on
the deployed server, run them with sudo in ~/ask-onboarding.
"""

from dataclasses import dataclass, field

from app.config import settings


@dataclass(frozen=True)
class Step:
    text: str
    command: str = ""


@dataclass(frozen=True)
class Runbook:
    kind: str
    meaning: str  # what people using the app experience
    causes: list[str]
    steps: list[Step]
    checks: list[str] = field(default_factory=list)  # "database", "model", "documents"
    document: str | None = None  # for document alerts: which file


def _model() -> Runbook:
    if settings.llm_provider == "anthropic":
        return Runbook(
            kind="model",
            meaning="Questions that need the model get an error instead of an answer. Off-topic questions are still "
            "refused, and tickets can still be opened (the draft starts from the question).",
            causes=[
                "The API key is missing, wrong or revoked.",
                "The account hit a rate limit or has no credit left.",
                "Anthropic's API had an outage or the server lost its internet connection.",
            ],
            steps=[
                Step(
                    "Check the key is set in .env (the value itself is never shown here).",
                    "grep -c ANTHROPIC_API_KEY= .env",
                ),
                Step("Look for the error the API returned.", "docker compose logs --tail 100 api | grep -i anthropic"),
                Step("After fixing the key, restart the API.", "docker compose up -d api"),
                Step(
                    "To keep answering meanwhile, switch to the local model: "
                    "set LLM_PROVIDER=ollama in .env, then restart.",
                    "docker compose up -d",
                ),
            ],
            checks=["model"],
        )
    return Runbook(
        kind="model",
        meaning="Questions that need the model get an error instead of an answer. Off-topic questions are still "
        "refused, and tickets can still be opened (the draft starts from the question).",
        causes=[
            "The Ollama container stopped, crashed or is restarting "
            "(the first answer after a restart takes about 30 s).",
            f"The model {settings.ollama_model} isn't downloaded yet (first start, or the volume was removed).",
            "The server ran out of memory: the model needs about 4 GB.",
        ],
        steps=[
            Step(
                "See whether Ollama is running. ollama-pull should show 'exited (0)'.",
                "docker compose ps ollama ollama-pull",
            ),
            Step("Start it again if it isn't running.", "docker compose up -d ollama"),
            Step(
                "If the model is missing, download it (about 1.9 GB).",
                f"docker compose exec ollama ollama pull {settings.ollama_model}",
            ),
            Step("Read the last messages from Ollama for the cause.", "docker compose logs --tail 100 ollama"),
            Step("Check free memory; give Docker at least 8 GB.", "free -h"),
            Step(
                "If it stays down, answer with Claude meanwhile: "
                "set LLM_PROVIDER=anthropic and ANTHROPIC_API_KEY in .env, then restart.",
                "docker compose up -d api",
            ),
        ],
        checks=["model"],
    )


def _database() -> Runbook:
    return Runbook(
        kind="database",
        meaning="Nothing works while the database is down: sign-in, answers, tickets and pages all fail. Alerts raised "
        "meanwhile are kept in memory and delivered once it's back.",
        causes=[
            "The db container stopped or is restarting.",
            "The disk is full, so Postgres stopped accepting writes.",
            "POSTGRES_PASSWORD in .env changed after the database was created, so the API can't sign in.",
        ],
        steps=[
            Step("See whether the database is running and healthy.", "docker compose ps db"),
            Step("Start it if it isn't.", "docker compose up -d db"),
            Step("Read its last messages for the cause.", "docker compose logs --tail 100 db"),
            Step("Check free disk space (Postgres needs room to write).", "df -h"),
            Step(
                "If the password changed, put the original POSTGRES_PASSWORD back in .env, then restart.",
                "docker compose up -d",
            ),
        ],
        checks=["database"],
    )


def _document(filename: str, error: str) -> Runbook:
    if "no extractable text" in error:
        causes = [
            "The file has no text layer: usually a scanned PDF or a photo of a page. The app doesn't do OCR.",
            "The file is empty, or contains only images.",
        ]
        steps = [
            Step("Open the original and check you can select its text."),
            Step("Export a version with text: 'Save as PDF' from the source document, or run OCR on the scan."),
            Step(f"Upload it again on the Documents page with the same name ({filename}): it replaces the failed one."),
        ]
    else:
        causes = [
            "The file is damaged or not really the type its name says.",
            "Processing failed unexpectedly (for example the embedding step ran out of memory).",
        ]
        steps = [
            Step(
                "Read the API's messages about this file.",
                f'docker compose logs --tail 200 api | grep -i -A5 "{filename}"',
            ),
            Step("Open the file to check it isn't damaged, and re-save it if needed."),
            Step(f"Upload it again with the same name ({filename}): it replaces the failed one."),
        ]
    return Runbook(
        kind="document",
        meaning=f"{filename} isn't in the assistant's library, "
        "so questions about its contents can't be answered from it. "
        "Every other document still works.",
        causes=causes,
        steps=steps,
        checks=["documents"],
        document=filename,
    )


def _startup_seed() -> Runbook:
    return Runbook(
        kind="startup",
        meaning="The sample documents didn't load on the first start, so the library may be empty.",
        causes=["The sample_docs folder isn't mounted or readable.", "The database wasn't ready yet."],
        steps=[
            Step("Check the folder is mounted into the API container.", "docker compose exec api ls /app/sample_docs"),
            Step("Read the startup messages.", "docker compose logs api | grep -i seed"),
            Step("Restart the API: it loads the samples whenever the library is empty.", "docker compose restart api"),
            Step("Or upload the documents yourself on the Documents page."),
        ],
        checks=["documents", "database"],
    )


def _server_error(key: str) -> Runbook:
    # key: error:<METHOD> <route>:<ExceptionType>
    where, _, error_type = key.removeprefix("error:").rpartition(":")
    return Runbook(
        kind="server error",
        meaning=f"Requests to {where} failed with an unexpected {error_type}. People saw 'Something went wrong on our "
        "side'. Other parts of the app are unaffected unless they have their own alerts.",
        causes=[
            "A bug the tests didn't catch, triggered by unusual input or data.",
            "A dependency (database, model, disk) failed in a way that endpoint didn't handle.",
        ],
        steps=[
            Step(
                "Find the full error (the traceback) in the API's messages.",
                f'docker compose logs --tail 300 api | grep -B2 -A30 "{error_type}"',
            ),
            Step("Check the live status below: if the database or model is down, fix that first."),
            Step("If it started after an update, see what changed and roll back if needed.", "git log --oneline -5"),
            Step("Report it with the traceback so it can be fixed and covered by a test."),
        ],
        checks=["database", "model"],
    )


def runbook_for(key: str, body: str = "") -> Runbook:
    """The runbook for an alert's dedupe key. body is the alert's message (used for document errors)."""
    if key == "model":
        return _model()
    if key == "database":
        return _database()
    if key.startswith("document:"):
        return _document(key.removeprefix("document:"), body)
    if key == "startup.seed":
        return _startup_seed()
    if key.startswith("error:"):
        return _server_error(key)
    return Runbook(
        kind="other",
        meaning="Something went wrong that has no specific guide yet.",
        causes=["See the alert's message."],
        steps=[Step("Read the API's recent messages.", "docker compose logs --tail 200 api")],
        checks=["database", "model"],
    )
