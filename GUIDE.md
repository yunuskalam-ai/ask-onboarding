# Ask Onboarding: a plain-language guide

This guide explains what Ask Onboarding does, who can do what, and what to expect, without technical terms. Developers will find the technical detail in [TECHNICAL.md](TECHNICAL.md).

## What it is

New employees have lots of questions: *How many days of holiday do I get? Can I deploy on a Friday? Where do I park?* The answers are usually somewhere in the handbook or the wiki, but finding them takes time.

Ask Onboarding is an assistant that **answers those questions from your company's own documents**. Three things make it trustworthy:

1. **Every answer shows its source.** Each fact has a small number, like **[1]**. Click it, and the original document opens with the exact sentence highlighted.
2. **It says when it doesn't know.** If the documents don't cover a question, it says *"I couldn't find this in the company documents"*. It doesn't guess or make things up.
3. **It hands unanswered questions to people.** When it can't answer, it offers to open a help-desk ticket, drafts it for you, and lets you check it before sending.

The assistant runs entirely on your own server. **Your documents are never sent to an outside AI company.**

## Who can do what

Everyone signs in, and each person has one of three roles:

| | Employee | Manager | Admin |
| --- | --- | --- | --- |
| Ask questions and see the sources | Yes | Yes | Yes |
| Open help-desk tickets | Yes | Yes | Yes |
| See tickets | Their own | Everyone's | Everyone's |
| Update a ticket's status and reply with a note | – | Yes | Yes |
| Add or replace company documents | – | – | Yes |
| Change people's roles | – | – | Yes |
| See the Overview (usage, gaps, activity) and the project docs | – | – | Yes |
| Notifications | About their own tickets | About all tickets | About all tickets, plus system problems |

These rules are enforced by the server itself, not just hidden in the screens. An employee can't reach a manager's functions even by trying the web address directly.

## A tour

### Signing in

The **home page** explains the assistant. Click **Sign in** and choose an account. *In this demo there are no passwords, so you simply pick a person. In a real company, people would sign in with their usual work login.*

The demo accounts are:
- **Sam Rivera** and **Priya Nair** (employees)
- **Jordan Lee** (manager)
- **Alex Morgan** (admin)

At the top right are your initials. Click them to **sign out**. Next to them:
- the **bell** shows your notifications
- the **☀ ☾ ◐** switch picks light mode, dark mode, or whatever your computer uses

### Asking a question (everyone)

On **Chat**, type a question the way you'd ask a colleague. While the assistant works, **three moving dots** show it's searching. The answer then appears word by word, usually within 10–20 seconds on this server.

- Click a **[number]** to open the source with the passage highlighted.
- If the answer is **"I couldn't find this in the company documents"**, you'll see **"Want the help desk to answer this?"**. Click **Yes, open a ticket**. The assistant writes a title and summary for you; check them, edit if needed, and click **Create ticket**. Nothing is sent until you confirm.

### Tickets

- **Employees** see **My tickets**: the questions they sent to the help desk, each with its status and any replies.
- **Managers and admins** see **All tickets**. They can move each one along and add a note for the person who asked:

  | Status | Meaning |
  | --- | --- |
  | **Open** | Not looked at yet |
  | **In progress** | Someone is working on it |
  | **Resolved** | Answered |
  | **Closed** | Finished; can be reopened |

- **Every change is kept in the ticket's history:** who, when, and their note.
- The **tabs** at the top filter by status and show how many tickets are in each.

### Notifications

The **bell** shows a red number when something new needs your attention. Click it to see the list, then click a notification to go straight to the ticket.

| Who | Is told about |
| --- | --- |
| Employees | Their own tickets, when the status changes or someone replies |
| Managers and admins | New tickets, and every change or reply on any ticket |
| Admins | **System problems** too, shown in red or amber: for example the assistant's model being unreachable, a document that couldn't be read, or a server error |

You're never notified about something you did yourself. If the same problem keeps happening, admins get **one** alert every 10 minutes, not a flood.

### Documents (admins)

**Documents** lists the library the assistant answers from. Admins upload PDF, Markdown (`.md`) and plain-text (`.txt`) files, up to 20 MB each. Word files aren't supported yet: save them as PDF first.
- A new file shows **processing**, then **ready** after a few seconds.
- Uploading a file with the same name **replaces** the old version straight away: the old text can no longer be quoted.
- If a file can't be read (for example a scanned PDF with no text in it), it shows **failed** with the reason, and admins get an alert.

### People (admins)

Lists everyone and their role. Change a role from the drop-down; it takes effect immediately, even for someone who is signed in. There must always be at least one admin.

### Overview (admins)

A one-page health check for the last 7, 30 or 90 days:

| Section | Shows |
| --- | --- |
| **Questions asked** and **answered from the documents** | How much the assistant is used, and how often it finds an answer |
| **Time to first word** | How long people wait |
| **Questions per day** | Answered in green, not answered in orange |
| **What the documents don't cover** | **The most-asked questions that got no answer. Each one is a document worth writing.** This is the most useful list for improving onboarding |
| **How questions ended** | Answered, not in the documents, off-topic, and so on |
| **Tickets by status**, **recent questions** and the **audit log** | Who signed in, uploaded, changed roles or updated tickets, and when |

### Docs (admins)

The project's own documentation, readable inside the app: this guide, the README, the architecture, the technical reference, testing and deployment.

## How the answers are kept honest

- The assistant is **only allowed to use the documents**, not its general knowledge. It must point to the source of every fact.
- **Two checks stop it from answering what the documents don't cover:**
  - if nothing in the library is even close to the question, it doesn't attempt an answer at all
  - if something is close but doesn't actually answer it, the assistant is required to say so
- **Instructions inside a document are ignored.** A document that says "ignore your rules" is treated as text, not obeyed.
- **The quality is measured**, not assumed. On 20 test questions it kept back for checking, it answered 94% of the answerable ones correctly, refused all 4 it should have refused, and never refused one it could answer. Every change to the system is re-checked against this test before it's released.

## Privacy and data

- **Documents, questions and answers stay on your server.** The assistant's model runs locally; nothing is sent to an outside AI service. (Using Claude instead is an option, but it's off by default.)
- **Admins can see the questions people ask, and who asked them** (in the Overview). That's how gaps in the documents are found. Tell employees this.
- **Tickets** are visible to the person who opened them and to managers and admins.
- **Notifications** are deleted after 180 days. Questions, tickets and the audit log are kept.
- **Sign-in** in this demo has no passwords, so the public demo is protected by a single site password. A real deployment would use the company's own login.

## When something goes wrong

| What you see | What it means | What happens |
| --- | --- | --- |
| "I couldn't find this in the company documents" | The documents don't cover it | Open a ticket; a person will answer |
| "Could not reach the local model" | The assistant's model is down or restarting | Admins are alerted automatically; try again in a minute |
| "Something went wrong on our side. The admins have been told." | An unexpected error | Admins get an alert with the details |
| A document shows **failed** | The file couldn't be read | Admins are alerted; usually the file has no text, such as a scanned image |
| "Please sign in" | Your session ended (after 7 days, or after signing out elsewhere) | Sign in again |

## Words used in this guide

| Word | Meaning |
| --- | --- |
| **Source** or **citation** | The numbered link after a fact, pointing to where it came from |
| **Ticket** | A question sent to the help desk because the documents didn't answer it |
| **Model** | The AI that writes the answer from the documents |
| **Library** | All the documents the assistant can answer from |
| **Session** | You being signed in; it ends when you sign out or after 7 days |

## What was built when

| Phase | What it covers |
| --- | --- |
| **Phase 1: the original brief** | Upload documents; answers with exact sources; honest "I don't know"; a drafted help-desk ticket; one-command setup; a measured quality test; smarter search that combines meaning and keywords |
| **Phase 2: refinements** | A home page; sign-in with employee, manager and admin roles; the ticket workflow with statuses, notes and history; notifications and admin alerts; the Overview; the Docs page; light and dark mode; the typing indicator; security hardening; automatic checks on every change; the public demo server |
