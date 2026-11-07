# AI log

How AI tools were used to build Ask Onboarding, where they were wrong, and how that was caught.

## Tools

| Tool | Used for |
| --- | --- |
| **Claude Code** (Claude Opus 5.5, in VS Code) | Reviewing the brief, writing the BRD and plan, writing the code, tests and docs, running Docker, the tests and the eval, and opening pull requests |
| **Claude Docs** | The BRD and project plan document, written at the start |
| **qwen2.5:3b via Ollama** | The product's own answering model (not a development tool) |

The work went one phase per branch, with one pull request per phase: 11 phases from setup to docs. Every PR was reviewed and merged by me on GitHub. The UI was checked by hand in a browser, because the assistant had no browser.

## Key prompts

Quoted with the spelling tidied up.

1. *"Here is the new project I received, please review this doc as expert and suggest the next step… make the BRD and initial project diagram."* This produced the BRD, the stack choice, the 2-day plan and the repo name.
2. *"Write the sample docs first, then push and open PR."* This produced 18 fictional company documents with consistent, checkable facts, with some topics left out on purpose for "no answer" tests.
3. *"We mentioned to use Ollama instead of Anthropic API key."* This switched the default LLM to a local model, so there's no key anywhere. I chose to run Ollama in Docker Compose, use qwen2.5:3b, and keep Claude as an option.
4. **My answer when the assistant asked how to read "Ticket tool call" in the brief:** "LLM tool call + confirm". This was my choice for FR-10: the model drafts the ticket through a real tool call, and a person approves it before saving.
5. *"Can we do any other part while this download is ongoing?"* The frontend was built while the Ollama image downloaded on a slow connection.
6. *"Put these architecture answers and a diagram, and complete the next steps"*, with the brief's six questions pasted in. This produced ARCHITECTURE.md, and the check of question 4 found a real bug (below).

## Where the AI was wrong, and how it was caught

| # | What went wrong | How it was caught | Fix |
| --- | --- | --- | --- |
| 1 | The "no answer" threshold was guessed at **0.35** | Measuring real scores: an unrelated passage already scored 0.38 | A calibration script with 24 questions set it to **0.55** ([eval/calibrate_threshold.py](eval/calibrate_threshold.py)) |
| 2 | The plan said a threshold would catch unanswerable questions | The same measurement: "stock options" scores 0.61–0.66, the same as real answers | A second guard: an exact refusal sentence in the prompt, detected in code |
| 3 | The plan recorded **Anthropic** as the LLM | **Me**: I pointed out that Ollama, with no key, had been agreed | Ollama became the default, and Claude stayed optional |
| 4 | A prompt tweak to make the 3B model cite sources | The assistant's own A/B test: it caused **wrong refusals** and garbage like a bare "[1]" | Reverted. A missing citation is less harmful than a wrong "I don't know" |
| 5 | Refusal detection matched only the exact sentence | **The eval**: the model refused in its own words, so the UI offered no ticket | Uncited paraphrases now count as refusals. Checked against all 60 saved answers: exactly 2 changed |
| 6 | The model warm-up used a different context size from chat | Live timing plus `ollama ps`: the model loaded twice | Warm-up and chat share one set of options |
| 7 | Two commits in the wrong order (code imported a function from the next commit) | The assistant noticed before pushing | The two commits redone in the right order |
| 8 | A PR description said "91 tests pass" before the full suite had run | The assistant re-ran the full suite before finishing | 91 confirmed |
| 9 | A latency of 1.5 s looked like a big win for "top 3 sources" | Reading every answer: Ollama had cached the prompt start from the previous run | The eval now reports prompt size as the fair speed measure |
| 10 | When the LLM was down, **opening a ticket failed** too | Writing ARCHITECTURE.md question 4, then stopping Ollama to check | The draft falls back to the question, and services restart automatically |
| 11 | Small chunks broke a retrieval test | Investigated instead of loosening the test: the "car parking" chunk lost its LONDON heading | Measured the tradeoff (hit@1 15→14 of 16, hit@5 unchanged), changed the test to top 3, and explained why. Hybrid search later restored rank 1 |
| 12 | Code-quality slips: a pointless monkeypatch, a too-clever comma expression, type annotations built by a function | Self-review before committing | Rewritten plainly |

## What I decided and did myself

- Chose the stack and the plan from the BRD, and later changed the LLM to a local model with no API key.
- Chose the ticket design: a model tool call plus human confirmation.
- Created the GitHub repository, installed WSL and Docker Desktop, and reviewed and merged every pull request.
- Checked the UI by hand: asking questions, clicking citations, creating a ticket.

## In my own words

<!-- TODO before submitting: write this section yourself, 5-10 sentences. For example: what surprised you, which AI output you didn't trust and checked, one part of the code you can now explain line by line, and what you would do differently. The graders read this section for honesty. -->
