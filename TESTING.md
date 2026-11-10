# Testing

How Ask Onboarding is tested, what the tests prove, the **negative and security tests** with their results, and what is *not* covered automatically.

Every number below comes from a real run on 10 Nov 2026 (last updated with the chat UI refresh). CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) re-runs everything on every pull request.

## Results at a glance

| Check | Tool | Result |
| --- | --- | --- |
| Backend tests | pytest | **509 passed**, 0 failed |
| Backend coverage | pytest-cov, branches included | **97.2%** (the build fails below 95%) |
| Frontend tests | vitest | **112 passed**, 0 failed |
| Python lint, including security rules | ruff with bandit (`S`) rules | 0 findings |
| Python formatting | ruff format | all 48 files formatted |
| Python types | mypy | 0 errors in 36 files |
| TypeScript types and production build | tsc, vite | 0 errors |
| TypeScript lint | oxlint `--deny-warnings` | 0 warnings |
| Known vulnerabilities, Python | pip-audit | 0 |
| Known vulnerabilities, npm | npm audit | 0 |
| Docs links and `#anchors` | scripts/check_links.py | all resolve, in 7 documents |
| Answer quality | [eval/run_eval.py](eval/run_eval.py) | 94% accuracy, 4/4 correct refusals, 0 false refusals (see [README](README.md#evaluation)) |

## How to run everything

One command runs every check CI runs. Run it before committing:

```bash
bash scripts/check.sh
```

Or step by step:

```bash
docker compose up -d db                    # the tests use a real Postgres, in a separate _test database

cd backend
pip install -r requirements-dev.txt
ruff check . && ruff format --check .      # lint (incl. security rules) and formatting
mypy                                       # types
pytest --cov --cov-fail-under=95           # all tests, with coverage
pip-audit                                  # known vulnerabilities

cd ../frontend
npm ci
npx oxlint --deny-warnings && npm test && npm run build && npm audit
```

The tests never touch your data: they use `ask_onboarding_test` and `ask_onboarding_eval`, created automatically next to the dev database.

## Strategy

| Layer | What is real | What is replaced, and why |
| --- | --- | --- |
| **Unit:** parsers, chunker, prompt helpers, SSE parser, redirect check | everything | nothing |
| **Integration:** ingestion, retrieval, sessions | **Postgres + pgvector**, SQL, transactions; the **real embedding model** for retrieval tests | a deterministic `fake_embed` where a test is about storage, not meaning (fast, offline) |
| **API:** every endpoint through FastAPI's TestClient | routing, validation, dependencies, cookies, role checks, database | the LLM is a scripted fake: answers must be repeatable, and a 3B model in CI would be slow and flaky |
| **LLM adapters** | our HTTP and SDK code | Ollama is a tiny local HTTP server; Claude is a fake SDK client. Both return canned replies and errors |
| **Security and negative tests** | everything above | the same as above |
| **Answer quality** | the full pipeline and the **real model** | nothing: [eval/run_eval.py](eval/run_eval.py), 20 held-out questions |

**The database is never mocked.** Most of the risky logic lives in SQL: replace-in-one-transaction, row locks, hybrid search, ownership filters. A mock would test our assumptions about Postgres instead of Postgres.

## Do the tests catch real breakage? (checked by breaking the code)

A test that can't fail proves nothing, so each new protection was removed temporarily and the suite re-run:

| Protection removed | Tests that failed |
| --- | --- |
| Origin check, session rotation, file headers, prompt filename escaping (all four together) | 7 of the 43 security tests, one or more per protection. The other 36 cover protections that already existed. |
| The coverage floor itself (raised to 98%, above the actual 97.4%) | the run exits with code 1: "Required test coverage of 98% not reached" |

Mistakes the checks caught during this work:
- **nginx forwarded the host without its port,** so every same-site POST would have been refused. Caught by testing through nginx, not only against the API.
- **A lint-suppression comment was placed inside a multi-line SQL string,** where it would have become part of the query. Caught by ruff, which still reported the error, then verified by the full suite.
- **A frontend test meant to check a backslash didn't contain one,** because of a TypeScript escape. Caught by the linter (`no-useless-escape`) and by the test itself.
- **Questions just after midnight were counted on the previous day** for anyone not in UTC. Days were grouped in UTC, and the browser also read `"2026-11-09"` as UTC midnight. Caught by **looking at a screenshot** of the Overview: the chart said 9 Nov, the question log said 10 Nov. Fixed both sides, with tests for three time zones.
- **A too-long line was committed** because only part of the checks had run. Caught before pushing. Since then, `scripts/check.sh` runs every CI check in one command.
- **Invisible no-break-space characters ended up in source files** through a shell-escaping slip. Caught by oxlint (`no-irregular-whitespace`); replaced with visible `\u00a0` escapes, and the source tree was scanned for any others.
- **A CSS class-name collision:** the notification icon used the class `ticket`, which already styles the ticket-offer box in the chat. Icons rendered off-centre. No test fails on that; a **screenshot** showed it, and the icon classes got their own names.
- **A test file took 4 minutes,** because one test made 105 real connection attempts to a database that isn't there. It now simulates the outage (the file runs in about 30 s), and two other tests still check the real connection path.
- **A test ran against the developer's real database.** It forgot the test-database fixture, and passed locally because that database had the tables. **CI caught it,** because its database is empty. Fixed, plus a guard in [conftest.py](backend/tests/conftest.py): during tests, the app's database dependency points at an error until a test explicitly chooses the test database. With the guard, the same slip fails locally with a clear message.

## Negative and security tests

Expected result means the server's answer. Every test listed passed in the run above.

### Signing in and sessions ([test_auth.py](backend/tests/test_auth.py), [test_security.py](backend/tests/test_security.py))

| Attempt | Expected | Test |
| --- | --- | --- |
| Any protected endpoint without a session (12 endpoints) | 401 | `test_signed_out_requests_get_401` |
| Sign in with an unknown email | 404, no cookie | `test_unknown_email_cannot_sign_in` |
| SQL injection in the sign-in email (`' OR 1=1 --`, `%`, `*@*`) | 404/422, no cookie | `test_sql_injection_in_sign_in_finds_no_account` |
| A forged session token | 401 | `test_made_up_session_tokens_are_refused` |
| Junk cookies: empty, 10,000 characters, SQL, path traversal | 401 | `test_junk_session_cookies_are_refused` |
| An expired session | 401 | `test_expired_sessions_are_refused` |
| Reusing a cookie after sign-out | 401 | `test_sign_out_ends_the_session_on_the_server` |
| Reusing the old cookie after switching accounts | 401, one session left | `test_switching_accounts_ends_the_previous_session` |
| Reading tokens from the database | only SHA-256 hashes are stored | `test_the_database_stores_only_a_hash_of_the_session_token` |
| Cookie flags | `HttpOnly`, `SameSite=Lax` (`Secure` in production) | `test_sign_in_sets_a_secure_session_cookie` |

### Who may do what ([test_auth.py](backend/tests/test_auth.py), [test_ticket_workflow.py](backend/tests/test_ticket_workflow.py))

| Attempt | Expected | Test |
| --- | --- | --- |
| An employee or manager uploads a document | 403, nothing stored or audited | `test_only_admins_upload_documents` |
| An employee or manager lists people or changes a role | 403 | `test_only_admins_manage_people` |
| An employee lists tickets | only their own | `test_employees_see_only_their_own_tickets_and_staff_see_all` |
| An employee changes a ticket's status, even their own | 403, unchanged | `test_employees_cannot_change_status_even_on_their_own_ticket` |
| Setting another person's name as the ticket owner | ignored: the owner comes from the session | `test_the_ticket_owner_comes_from_the_session_not_the_request` |
| Demoting the last admin | 409, still admin | `test_the_last_admin_cannot_be_demoted` |
| An unknown role (`owner`), or an unknown user | 422 / 404 | `test_bad_role_changes_are_rejected` |
| A demoted user's existing session | loses the rights at once | `test_admin_changes_a_role_and_it_applies_at_once`, `test_an_admin_can_step_down_when_another_admin_exists` |
| An unknown status (`done`), an over-long note, an unknown ticket | 422 / 422 / 404 | `test_bad_changes_are_rejected` |
| A "change" that changes nothing | 400, no history entry | `test_a_change_that_changes_nothing_is_refused` |

### Cross-site requests, CSRF ([test_security.py](backend/tests/test_security.py))

| Attempt | Expected | Test |
| --- | --- | --- |
| Sign-in POST from another origin | 403, no session created | `test_cross_site_sign_in_is_blocked_and_creates_no_session` |
| Status change from another origin | 403, unchanged | `test_cross_site_status_change_is_blocked` |
| Upload from another origin | 403, nothing stored | `test_cross_site_upload_is_blocked` |
| Origin matching: neighbouring `*.sslip.io` host, other port, look-alike suffix, `null`, empty, garbage | all refused (10 cases) | `test_same_origin` |
| The app's own requests, and non-browser clients without an Origin | allowed | `test_same_origin_and_originless_requests_pass` |

### Injection ([test_security.py](backend/tests/test_security.py), [test_chat.py](backend/tests/test_chat.py))

| Attempt | Expected | Test |
| --- | --- | --- |
| `'); DROP TABLE users; --` in a ticket | stored as text, table intact | `test_sql_injection_in_a_ticket_is_stored_as_text` |
| A document containing `</source>` plus instructions | can't close its tag in the prompt | `test_a_document_cannot_close_its_source_tag`, `test_a_source_cannot_close_its_own_tag` |
| A filename with quotes and fake `<system>` tags | escaped inside `file="..."` | `test_a_filename_cannot_break_out_of_the_prompt_tag` |
| A filename containing CR/LF plus `Set-Cookie` | no header injected; the name is URL-encoded | `test_a_filename_cannot_inject_response_headers` |

### Uploaded files ([test_security.py](backend/tests/test_security.py), [test_documents_api.py](backend/tests/test_documents_api.py), [test_parsers.py](backend/tests/test_parsers.py), [test_ingest_service.py](backend/tests/test_ingest_service.py))

| Attempt | Expected | Test |
| --- | --- | --- |
| A `.txt` file containing `<script>` | served as `text/plain` with `nosniff` and CSP `sandbox` | `test_text_files_are_served_inert` |
| A PDF | `nosniff`, viewable (no sandbox, which Chrome would refuse) | `test_pdfs_are_served_with_nosniff_and_viewable` |
| `.docx` / `.exe` / `.pptx` | 415, nothing stored, no internals in the error | `test_unsupported_file_type_gets_a_clear_415`, `test_errors_do_not_leak_internals`, `test_unsupported_type_is_rejected_before_anything_is_stored` |
| A file over 20 MB | 413 | `test_file_over_the_size_limit_is_rejected` |
| A corrupt PDF, a whitespace-only file | rejected or marked failed, with a reason | `test_corrupt_pdf_is_rejected`, `test_whitespace_only_file_is_rejected`, `test_file_with_no_text_is_marked_failed` |
| The embedding model fails mid-upload | document marked failed; the API keeps running | `test_embedding_error_is_marked_failed_without_crashing` |
| A slow job finishing after a newer upload | never overwrites the newer version | `test_slow_job_does_not_overwrite_a_newer_upload` |

### Malformed requests ([test_security.py](backend/tests/test_security.py), [test_chat.py](backend/tests/test_chat.py), [test_retrieval.py](backend/tests/test_retrieval.py), [test_tickets.py](backend/tests/test_tickets.py))

| Attempt | Expected | Test |
| --- | --- | --- |
| Broken JSON, form encoding, `null`, a list instead of text, a bad history, an 8,001-character turn, 51 turns | 422 before any work | `test_malformed_chat_requests_are_rejected_before_any_work`, `test_chat_endpoint_validates_input` |
| Empty, whitespace-only or 1,001-character questions; `top_k` of 0 or 21 | 422 | `test_retrieve_endpoint_validates_input` |
| Blank or over-long ticket fields | 422, nothing saved | `test_invalid_tickets_are_rejected` |
| Non-numeric or negative IDs in URLs | 404/422 | `test_malformed_ids_are_rejected` |

### The model and its failures ([test_llm.py](backend/tests/test_llm.py), [test_llm_anthropic.py](backend/tests/test_llm_anthropic.py), [test_chat.py](backend/tests/test_chat.py), [test_tickets.py](backend/tests/test_tickets.py))

| Situation | Expected | Test |
| --- | --- | --- |
| Ollama not running, model not downloaded, error mid-stream, unreadable reply | a clear `LLMError` message, never a stack trace | `test_ollama_not_running_gives_a_clear_message`, `test_missing_model_gives_a_clear_message`, `test_error_in_the_stream_becomes_llm_error`, `test_unreadable_reply_becomes_llm_error` |
| Claude: bad key (401), rate limit (429), server error (500), connection error, timeout | a clear `LLMError` for answers and ticket drafts | `test_api_failures_become_clear_llm_errors` (5 cases) |
| Claude without an API key | fails before calling the API | `test_no_api_key_fails_before_calling_the_api` |
| The model refuses on safety grounds | "not answered", ticket offered | `test_a_refusal_becomes_llm_refused`, `test_safety_refusal_is_reported_as_not_answered` |
| Off-topic question | answered "not in the documents" **without calling the model** | `test_low_score_answers_no_without_calling_the_llm`, `test_off_topic_question_never_reaches_the_llm` |
| Keyword-only matches on an off-topic question | still refused | `test_keyword_matches_cannot_lift_a_question_over_the_threshold` |
| No tool call, the wrong tool, invalid or over-long arguments | no draft, or a validated and cut draft | `test_no_tool_call_gives_no_draft`, `test_a_different_tool_name_is_ignored`, `test_tool_arguments_are_validated`, `test_overlong_tool_arguments_are_cut`, `test_no_valid_tool_call_gives_no_draft` |
| The model is down while opening a ticket | the draft falls back to the question; never blocked | `test_draft_still_works_when_the_model_is_down` |
| Documents still processing or failed | never used as sources | `test_documents_that_are_not_ready_are_never_returned`, `test_hybrid_never_returns_documents_that_are_not_ready` |

### Admin overview and the question log ([test_admin.py](backend/tests/test_admin.py), [test_question_log.py](backend/tests/test_question_log.py))

| Attempt | Expected | Test |
| --- | --- | --- |
| Overview, question log or audit log while signed out | 401 | `test_signed_out_gets_401` |
| The same as an employee or manager (2 roles × 3 endpoints) | 403 | `test_non_admins_get_403` |
| `days` of 0, 366 or `abc`; `limit` of 0, 201 or 1000; a negative `offset` | 422 | `test_out_of_range_parameters_are_rejected` |
| `tz` of `Mars/Olympus_Mons`, `UTC; DROP TABLE users`, `../../etc`, 65 characters, empty | 422 (checked against Postgres's own time zone list) | `test_unknown_time_zones_are_rejected` |
| An empty system | zeros and "–", never a division by zero | `test_an_empty_system_gives_zeros_not_errors` |
| The question log can't be written (database down) | the answer still streams in full; the failure is logged | `test_a_logging_failure_never_breaks_the_answer` |
| The browser leaves mid-answer | logged once as `stopped` | `test_a_browser_leaving_mid_answer_is_logged_as_stopped` |
| A crash inside the answer stream | still logged | `test_a_crash_inside_the_stream_is_still_logged` |
| An actor deleted after acting | the audit entry stays, as "Deleted user" | `test_the_audit_log_names_the_actor_and_survives_their_deletion` |

### Audit log: IP, location and device ([test_audit_context.py](backend/tests/test_audit_context.py))

| Attempt or situation | Expected | Test |
| --- | --- | --- |
| A client reaching the API directly sends `X-Real-IP: 94.200.12.7` | **ignored**: its real address is recorded | `test_a_client_reaching_the_api_directly_cannot_fake_its_ip`, `test_client_ip_believes_x_real_ip_only_from_a_private_peer` |
| A junk `X-Real-IP`, a peer that isn't an address | ignored / no IP | same |
| A download that isn't a database (an HTML error page) | refused; **the old database stays** | `test_a_bad_download_leaves_the_old_database_in_place` |
| This month's file not published yet | last month's is used | `test_a_missing_database_is_downloaded_falling_back_to_last_month` |
| No database, or a damaged one | no location, and sign-in still works | `test_no_database_means_no_location_not_an_error`, `test_a_damaged_database_means_no_location_not_an_error` |
| Office and local addresses (10.x, 192.168.x, 127.0.0.1, ::1, fe80::) | "Private network", without any database | `test_office_and_local_addresses_are_a_private_network_without_any_database` |
| 13 browser strings, from Chrome on Windows to an iPad, curl and nonsense | the right browser, system and device; unknown is None, never a guess | `test_describe_reads_common_browsers_and_never_guesses` |
| The startup download fails | logged; the API keeps starting | `test_no_ip_location_database_is_only_logged` |

**Tests never download.** An autouse fixture in conftest makes any download fail and points the app at an empty folder.

**Checked live:**
- **Real lookups** with the real database (November 2026): 94.200.12.7 → Warisan, UAE; 8.8.8.8 → Mountain View, US; 81.2.69.142 → London, UK; an IPv6 address → Frankfurt, Germany.
- **Through Caddy 2.10.2 and nginx**, a forged `X-Forwarded-For: 8.8.8.8` was dropped and the real peer was recorded.
- **DB-IP refuses Python's default User-Agent (403),** which the first live run caught. The app now names itself.

### Notifications ([test_notifications.py](backend/tests/test_notifications.py))

| Attempt | Expected | Test |
| --- | --- | --- |
| An employee's ticket gets an update | the owner and all staff are told; **other employees never are**; the person who made the change isn't told about it | `test_a_status_change_notifies_the_owner_and_staff_but_not_the_actor` |
| A new ticket | every manager and admin, not its author, no other employee | `test_a_new_ticket_notifies_every_manager_and_admin_but_not_its_author` |
| Reading or marking someone else's notification, or one that doesn't exist | 404 either way, so nobody can probe which exist | `test_someone_elses_notification_cannot_be_read_or_marked` |
| A cross-site "mark all as read" | 403, nothing changed | `test_cross_site_mark_all_read_is_blocked` |
| Saving the notifications fails during a ticket change | the whole change rolls back: no half-saved ticket | `test_a_ticket_change_and_its_notifications_are_saved_together_or_not_at_all` |
| System alerts | admins only | `test_alerts_go_to_admins_only` |
| The same failure repeated, or 8 failures **at the same moment** | one alert per 10 minutes (a database lock stops simultaneous duplicates) | `test_the_same_problem_alerts_once_per_window`, `test_simultaneous_failures_still_alert_once` |
| The database is down when an alert is raised | no crash; the alert waits in memory and is delivered when the database is back | `test_alerts_wait_while_the_database_is_down_and_arrive_after`, `test_the_delivery_loop_retries_until_stopped` |
| A long outage | the waiting queue is capped (100) and drops the oldest first | `test_the_waiting_queue_is_bounded` |
| An unexpected server error | a plain 500 with no internals; admins alerted with the endpoint and error type | `test_an_unexpected_error_gives_a_plain_500_and_alerts_admins` |
| Bad paging (`limit` 0 or 101, `before` 0 or `abc`), signed out | 422 / 401 | `test_bad_paging_is_rejected`, `test_signed_out_gets_401` |

Checked end to end on the real stack: Sam opened a ticket and Jordan resolved it with a note. Then **the model was stopped** and a question asked. Sam was told about his own ticket only; Jordan about the new ticket only; Alex about both, plus a red "The answer model failed" alert. In headless Edge, clicking Sam's notification opened `/tickets#ticket-6`, with the ticket highlighted and the badge cleared.

### Project docs ([test_docs_api.py](backend/tests/test_docs_api.py), [docsLinks.test.ts](frontend/src/docsLinks.test.ts))

| Attempt | Expected | Test |
| --- | --- | --- |
| `.env`, `README.md` (a path, not a name), `..%2F.env`, encoded `../`, a wrong extension, `chat.png.exe` | 404, and the secret never appears in the response | `test_nothing_outside_the_list_can_be_read` (10 cases) |
| An employee or manager | 403 for the list, a document and an image | `test_only_admins` |
| An SVG or PNG from `docs/` | `nosniff` and CSP `sandbox` | `test_images_are_served_inert` |
| Links in a document: `javascript:`, `data:`, `//host`, `vbscript:`, climbing out of the repo | not followed | `resolveLink` tests |
| Images: an external URL, `data:`, `docs/../.env`, a sub-folder, upper case | not loaded | `resolveImage` tests |

### People, departments and reporting lines ([test_people.py](backend/tests/test_people.py), [test_ticket_workflow.py](backend/tests/test_ticket_workflow.py), [teamTree.test.ts](frontend/src/teamTree.test.ts))

| Attempt | Expected | Test |
| --- | --- | --- |
| A duplicate email, a malformed email, a blank name, an unknown role, manager or department | 409 / 422, nobody added | `test_bad_new_people_are_refused` |
| Reporting to an employee, or to an inactive manager | 422 | `test_only_managers_and_admins_can_have_reports`, `test_an_inactive_manager_cannot_take_new_reports` |
| Reporting to yourself; a loop 2, 3 or 5 levels deep | 422, nothing changed | `test_nobody_reports_to_themselves`, `test_reporting_loops_are_refused_at_any_depth` |
| Deactivating yourself; demoting the last **active** admin | 409 | `test_an_admin_cannot_deactivate_themselves`, `test_the_last_active_admin_cannot_be_demoted_or_deactivated` |
| **Two admins deactivating each other at the same moment** | one is refused; exactly one active admin remains | `test_two_admins_deactivating_each_other_at_once_leave_one_admin` |
| A deactivated person's open session, sign-in, and place on the sign-in list | 401 / 403 / gone, sessions deleted | `test_deactivating_signs_the_person_out_and_hides_them_from_sign_in` |
| Making a manager with reports an employee | 409 "Reassign them first" | `test_a_manager_with_reports_cannot_become_an_employee` |
| A duplicate department name (any case); deleting a department with people | 409 | `test_department_names_are_unique_ignoring_case`, `test_a_department_with_people_cannot_be_deleted` |
| Employees or managers using any people or department endpoint (14 cases) | 403 | `test_only_admins_manage_people_and_departments` |
| A manager seeing or changing another team's ticket | not listed; 404, the same as a missing ticket | `test_a_manager_cannot_see_or_change_another_teams_ticket` |
| A manager changing their **own** ticket | 403; their manager or an admin can | `test_a_manager_cannot_change_their_own_ticket` |
| Notifications for another team's manager, or an inactive manager | none | `test_another_teams_manager_hears_nothing`, `test_inactive_people_receive_nothing` |
| A loop or a missing manager in the data shown on the People page | everyone still shown once, no hang | `buildTree` tests |
| Saving a People edit form with nothing changed, or clearing a department | Save stays disabled; only changed fields are sent, a cleared field as `null` | `changesFrom` tests |

### Alert details and live checks ([test_alerts.py](backend/tests/test_alerts.py))

| Situation | Expected | Test |
| --- | --- | --- |
| The database can't be reached | the check says so, with no exception | `test_the_database_check` |
| Ollama unreachable; running but the model isn't downloaded | each reported in plain words | `test_the_model_check_spots_an_unreachable_server`, `test_the_model_check_spots_a_missing_model` |
| **The hostname lookup hangs** (a stopped container) | the check gives up after its deadline, well under a second in the test | `test_the_model_check_answers_quickly_even_when_the_lookup_hangs` |
| Claude configured or missing its key | judged by configuration, never by a paid call | `test_the_model_check_for_claude_never_spends_tokens` |
| A failed, stuck or deleted document | reported per file, and for the library | `test_the_documents_check`, `test_a_stuck_document_is_reported` |
| Every kind of alert key, including an unknown one | a runbook with meaning, causes and steps | `test_every_alert_kind_has_a_runbook_with_steps` |
| The same problem repeating | one alert counting its occurrences; a new one after 10 quiet minutes | `test_the_same_problem_alerts_once_per_window` |
| A ticket notification, or a missing id, at `/admin/alerts/{id}` | 404 | `test_a_ticket_notification_is_not_an_alert` |
| Employees, managers, signed out | 403 / 401 | `test_only_admins_see_alerts_and_status`, `test_signed_out_gets_401` |

Checked live: with Ollama stopped, two questions produced **one alert counted twice**. Its page showed "Still failing" and six fix steps, and loaded in 1.6 s (it took 4 s before the deadline fix). After starting Ollama, the same page showed "Recovered". There were no console or CSP errors.

### Document access ([test_document_access.py](backend/tests/test_document_access.py))

| Attempt | Expected | Test |
| --- | --- | --- |
| An employee lists the library | 403, but documents their answers cite still open | `test_employees_can_still_open_what_answers_cite` |
| An employee or manager deletes a document | 403, nothing deleted | `test_only_admins_delete` |
| A cross-site delete | 403, nothing deleted | `test_a_cross_site_delete_is_blocked` |
| Deleting a missing or malformed id | 404 / 422 | `test_deleting_a_missing_document` |
| Deleting while the document is still processing | the job finds it gone and stores nothing | `test_deleting_while_still_processing_stores_nothing` |
| After a delete | no chunks remain, search returns nothing from it, audited | `test_an_admin_deletes_a_document_and_answers_stop_using_it` |

Checked in headless Edge: Sam (employee) has no Documents tab, and the page says "Not available for your role". Jordan (manager) sees the library read-only. Alex (admin) sees the upload button and 18 Delete buttons.

### Renaming the demo company ([test_rename.py](backend/tests/test_rename.py))

| Situation | Expected | Test |
| --- | --- | --- |
| Demo accounts on the old domain | moved to `@yklabs.example` once; other addresses untouched | `test_demo_emails_move_to_the_new_domain_once` |
| The new address is already taken | nothing overwritten | `test_a_taken_new_address_is_never_overwritten` |
| Refreshing the samples | only same-named, changed documents are replaced; safe to run again | `test_refresh_replaces_only_changed_samples` |

Checked on the real dev database: 4 demo accounts renamed, 16 changed samples replaced (a second run replaced 0), and no stored passage mentions the old name. The retrieval eval gives exactly the same hit@1/3/5 as before the rename.

### Settings ([test_config.py](backend/tests/test_config.py))

| Attempt | Expected | Test |
| --- | --- | --- |
| `LLM_PROVIDER=openai` or `Ollama`, `SEARCH_MODE=keyword`, `ANSWER_EFFORT=extreme` or empty | startup stops with a message naming the setting | `test_a_value_outside_the_allowed_set_fails_at_startup` |
| `OLLAMA_URL` of `file:///etc/passwd`, `ftp://…`, no scheme, empty, `javascript:` | startup stops | `test_the_ollama_url_must_be_http` |
| `CHUNK_SIZE=five` | startup stops | `test_numbers_must_be_numbers` |

### Frontend ([redirect.test.ts](frontend/src/redirect.test.ts), [api.test.ts](frontend/src/api.test.ts))

| Attempt | Expected |
| --- | --- |
| `?next=` of `https://evil.example`, `//evil.example`, `/\evil.example`, `\\evil.example`, `javascript:…`, a relative path, a leading space | ignored; goes to `/chat` (9 cases) |
| The API answers 401 | the app returns to sign-in |
| The API answers 403 | the server's message is shown and the user stays signed in |
| A 502 error page in HTML | a readable "Request failed (502)" |

## Checked live, not in the automated suite

**In a real browser.** Headless Microsoft Edge is driven over the Chrome DevTools Protocol, signed in as the admin. It opens every page (home, chat, documents, tickets, people, overview) in **light and dark** mode and records console errors, warnings and CSP violations: **none on any page**. It also screenshots the Overview for a visual check, and hovers the chart to confirm the readout works. Those screenshots caught the time-zone bug below.

Also run against the real Docker stack, through nginx, with `curl`:
- **Security headers:** CSP, `nosniff`, `X-Frame-Options`, `Referrer-Policy` and `Permissions-Policy` on pages; `nosniff` and frame denial on the API.
- **No inline scripts:** the built page contains none, so the strict CSP holds.
- **The Origin check through nginx:** same-site 200, another site 403, same host on another port 403.
- **The API container runs as uid 1000,** not root.
- **The deployed site:** a valid Let's Encrypt certificate, http redirects to https, the login is enforced, and the database, API and model ports are closed. See [deploy/README.md](deploy/README.md).

## What is not covered automatically

- **Browser end-to-end tests** (clicking through the UI). The UI was checked by hand in a browser. Playwright tests would be the next step; they need the whole stack, including a model, in CI.
- **The browser check isn't in CI.** It was run locally with headless Edge (see above); adding it to CI would mean running the whole stack there.
- **Load and performance tests.** First-token latency is measured by the eval, but there are no concurrency tests. The single-CPU model is the known bottleneck; see [ARCHITECTURE.md](ARCHITECTURE.md).
- **Answer quality beyond the 20 eval questions.** One question is 6 points of accuracy; see ARCHITECTURE.md §5 for the plan to grow the set.
- **Rate limiting** isn't implemented, so it isn't tested. The deployed demo sits behind a site-wide password.

## Coverage by module

From `pytest --cov` (statements and branches):

| Module | Coverage | Not covered |
| --- | --- | --- |
| `app/auth.py`, `app/security.py`, `app/client_info.py`, `app/useragent.py`, `app/question_log.py`, `app/notifications.py`, `app/runbook.py`, `app/api/admin.py`, `app/api/notifications.py`, `app/api/docs.py`, `app/api/users.py`, `app/api/chat.py`, `app/api/retrieve.py`, `app/chat/prompt.py`, `app/ingest/*` (parsers, chunker, embedder), `app/retrieval/search.py` | 100% | – |
| `app/api/tickets.py` | 99% | the default ticket-drafter getter (replaced in tests) |
| `app/api/auth.py`, `app/main.py`, `app/deps.py`, `app/ingest/service.py`, `app/chat/service.py`, `app/geoip.py` | 96–98% | default dependency getters, one log-only branch, the database reader's cache hit |
| `app/startup.py` | 84% | log-only lines after a successful backfill or prune, and their failure branches |
| `app/api/documents.py` | 95% | the default embedder getter, a document deleted mid-request |
| `app/chat/llm.py` | 94% | the defensive "unknown provider" branches (settings validation now rejects these at startup) and one stream-closing edge |
| `app/config.py`, `app/db.py`, `app/reindex.py` | 88–91% | `if __name__ == "__main__"` and error branches for impossible states |
| **Total** | **97.2%** | |
