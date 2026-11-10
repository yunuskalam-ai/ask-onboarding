# AI log

How AI tools were used to build Ask Onboarding, where they were wrong, and how that was caught.

## Tools

| Tool | Used for |
| --- | --- |
| **Claude Code** (Claude Opus 5.5, in VS Code) | Reviewing the brief, writing the BRD and plan, writing the code, tests and docs, running Docker, the tests and the eval, and opening pull requests |
| **Claude Docs** | The BRD and project plan document, written at the start |
| **qwen2.5:3b via Ollama** | The product's own answering model (not a development tool) |

**Phase 1** (the brief) went one phase per branch, with one pull request per phase: 11 phases from setup to docs. **Phase 2** (refinements I asked for after that) followed the same rule: one feature per branch and pull request (#18 to #34). Every PR was reviewed and merged by me on GitHub.

In Phase 1 I checked the UI by hand in a browser. In Phase 2 the assistant also drove a headless Edge browser itself: it read every page for console and security-policy errors, and took screenshots to compare before and after each UI change.

## Key prompts

Quoted with the spelling tidied up.

1. *"Here is the new project I received, please review this doc as expert and suggest the next step… make the BRD and initial project diagram."* This produced the BRD, the stack choice, the 2-day plan and the repo name.
2. *"Write the sample docs first, then push and open PR."* This produced 18 fictional company documents with consistent, checkable facts, with some topics left out on purpose for "no answer" tests.
3. *"We mentioned to use Ollama instead of Anthropic API key."* This switched the default LLM to a local model, so there's no key anywhere. I chose to run Ollama in Docker Compose, use qwen2.5:3b, and keep Claude as an option.
4. **My answer when the assistant asked how to read "Ticket tool call" in the brief:** "LLM tool call + confirm". This was my choice for FR-10: the model drafts the ticket through a real tool call, and a person approves it before saving.
5. *"Can we do any other part while this download is ongoing?"* The frontend was built while the Ollama image downloaded on a slow connection.
6. *"Put these architecture answers and a diagram, and complete the next steps"*, with the brief's six questions pasted in. This produced ARCHITECTURE.md, and the check of question 4 found a real bug (below).

**Phase 2:**

7. A screenshot of another team's app, with *"take the inspiration, as our design must be unique and uncopied"*. This started the home page, sign-in and the three roles. I chose a no-password demo sign-in.
8. *"Ensure the code quality, security, testing are top notch, it must also include negative testing and its result."* This produced the security hardening, CI with a coverage floor, and [TESTING.md](TESTING.md).
9. *"The admin should receive any system, app, database failure/error"*, and later *"the error should also suggest the solution in real time."* These produced notifications, admin alerts and the alert pages with fix steps.
10. *"Whole web is sloppy, I need a UI/UX audit."* The assistant listed 8 problems, with screenshots, and fixed them in three PRs.
11. *"In the audit log table let's also add the IP, system, device, location."* I chose an offline location database, so no employee IP is sent anywhere.

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
| 13 | A firewall step in the server setup script was "fixed" by an edit that **silently never applied** | Running the script on the real server | Every scripted edit now asserts it matched exactly once |
| 14 | nginx forwarded the host without its port, so the new cross-site check refused **every** same-site request | Testing through nginx, not only the API | nginx forwards `$http_host` |
| 15 | A test ran against **my real development database** | CI, whose database is empty | A guard makes any test that forgets the test database fail |
| 16 | The Overview counted days in UTC: a question at 00:30 in Dubai landed on the previous day | Looking at a screenshot | Days follow the viewer's time zone, tested in three zones |
| 17 | A commit message described a change that wasn't in the commit | Reviewing the pull request before merging | A follow-up commit with the missing change |
| 18 | Two "stacked" PRs merged into feature branches instead of `main` | Checking `main` after I said "merged" | A catch-up PR; every PR now targets `main` |
| 19 | A startup test **downloaded the real 127 MB location database** | The file appearing on disk during a test run | Tests now refuse any download |
| 20 | The location database download failed with 403 on its first live run | The live run's log: the site blocks Python's default client name | The app names itself in the request |

## What I decided and did myself

- Chose the stack and the plan from the BRD, and later changed the LLM to a local model with no API key.
- Chose the ticket design: a model tool call plus human confirmation.
- Created the GitHub repository, installed WSL and Docker Desktop, and reviewed and merged every pull request.
- Checked the UI by hand: asking questions, clicking citations, creating a ticket.
- **Phase 2:** asked for every refinement; chose a no-password demo sign-in, managers seeing only their own team's tickets, and an offline location database for the audit log; picked Google Cloud for the demo server after the free tiers elsewhere ran out; set up the server myself in the browser's SSH window; and asked for the final UI and documentation audits.

## In my own words

- I used AI a lot, but I learned not to trust it blindly. It recorded a paid API (Anthropic) as our plan even though we had agreed on Ollama with no API key. I noticed and corrected it.
- I asked for negative tests and proof, not just "tests pass", because passing tests don't show what the app rejects.
- I didn't want to copy another app's design. I used it only as inspiration and asked for something original.
- When I looked at the finished app, I honestly thought it was sloppy. That led to a full UI audit and three fixes.
- Deployment was harder than I expected. Hugging Face needed a paid plan, Oracle had no capacity, and on Google Cloud, `sudo` kept timing out in the browser SSH window. I set up the server myself in the end.
- IP-based location is rough. The audit log placed my own sign-in in Karachi.
- What I'd do differently: check where a PR is going before merging, and look at the app with fresh eyes earlier instead of waiting until the end.
