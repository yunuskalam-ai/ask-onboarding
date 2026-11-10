// Plain-language labels and formatting for the admin overview. Kept apart from
// the page so they can be unit-tested.

import type { AuditEntry, Outcome } from "./api";

export const OUTCOME_LABEL: Record<Outcome, string> = {
  answered: "Answered",
  not_in_sources: "Not in the documents",
  low_score: "Off-topic (model not asked)",
  refused: "Declined by the model",
  error: "Model error",
  stopped: "Stopped by the user",
};

export const OUTCOME_ORDER: Outcome[] = ["answered", "not_in_sources", "low_score", "refused", "error", "stopped"];

const NBSP = "\u00a0"; // keeps a number and its unit on one line

/** 1234 -> "1.2 s", 640 -> "0.6 s", null -> "–" */
export function seconds(ms: number | null): string {
  return ms === null ? "–" : `${(ms / 1000).toFixed(1)}${NBSP}s`;
}

/** 0.6 -> "60%", null -> "–" */
export function percent(rate: number | null): string {
  return rate === null ? "–" : `${Math.round(rate * 100)}%`;
}

/** 3.25 -> "3.3 h"; under an hour in minutes; null -> "–" */
export function hours(h: number | null): string {
  if (h === null) return "–";
  return h < 1 ? `${Math.max(1, Math.round(h * 60))}${NBSP}min` : `${h.toFixed(1)}${NBSP}h`;
}

/** count(1, "manager") -> "1 manager", count(2, "manager") -> "2 managers" */
export function count(n: number, noun: string): string {
  return `${n}${NBSP}${n === 1 ? noun : `${noun}s`}`;
}

/**
 * "2026-11-09" -> that calendar day at local midnight. new Date("2026-11-09")
 * would mean midnight UTC, which shows as the 8th anywhere west of UTC.
 */
export function localDate(isoDay: string): Date {
  const [year, month, day] = isoDay.split("-").map(Number);
  return new Date(year, month - 1, day);
}

const STATUS_WORD: Record<string, string> = {
  open: "Open",
  in_progress: "In progress",
  resolved: "Resolved",
  closed: "Closed",
};

const text = (value: unknown) => (typeof value === "string" || typeof value === "number" ? String(value) : "?");

type Change = { old?: unknown; new?: unknown };

/** "role employee → manager, deactivated, new manager": what a People edit changed.
 *  Departments and managers are stored by id, so they're named only as changed. */
function describeChanges(changes: unknown): string {
  if (!changes || typeof changes !== "object") return "";
  const parts: string[] = [];
  for (const [field, raw] of Object.entries(changes as Record<string, Change>)) {
    const change = raw ?? {};
    if (field === "role") parts.push(`role ${text(change.old)} → ${text(change.new)}`);
    else if (field === "name") parts.push(`name ${text(change.old)} → ${text(change.new)}`);
    else if (field === "active") parts.push(change.new ? "reactivated" : "deactivated");
    else if (field === "department_id") parts.push("new department");
    else if (field === "manager_id") parts.push("new manager");
    else parts.push(field);
  }
  return parts.join(", ");
}

/** "Chrome 131 on Windows", or whichever half is known, or a dash. */
export function describeClient(entry: Pick<AuditEntry, "browser" | "os">): string {
  if (entry.browser && entry.os) return `${entry.browser} on ${entry.os}`;
  return entry.browser ?? entry.os ?? "–";
}

/** One readable line per audit entry, e.g. "Changed sam@… from employee to manager". */
export function describeAudit(entry: AuditEntry): string {
  const d = entry.details;
  switch (entry.action) {
    case "sign_in":
      return "Signed in";
    case "sign_out":
      return "Signed out";
    case "document.upload":
      return d.unchanged ? `Re-uploaded ${text(d.filename)} (unchanged)` : `Uploaded ${text(d.filename)}`;
    case "document.delete":
      return `Deleted ${text(d.filename)}`;
    case "user.add":
      return `Added ${text(d.user)} as ${text(d.role)}`;
    case "user.change": {
      const what = describeChanges(d.changes);
      return what ? `Updated ${text(d.user)}: ${what}` : `Updated ${text(d.user)}`;
    }
    case "user.role": // entries written before people management (Phase 2, PR #24)
      return `Changed ${text(d.user)} from ${text(d.old)} to ${text(d.new)}`;
    case "department.add":
      return `Added the ${text(d.name)} department`;
    case "department.rename":
      return `Renamed the ${text(d.old)} department to ${text(d.new)}`;
    case "department.delete":
      return `Deleted the ${text(d.name)} department`;
    case "ticket.create":
      return `Opened ticket #${text(d.ticket)}: ${text(d.title)}`;
    case "ticket.status":
      return `Moved ticket #${text(d.ticket)} from ${STATUS_WORD[text(d.old)] ?? text(d.old)} to ${
        STATUS_WORD[text(d.new)] ?? text(d.new)
      }`;
    default:
      return entry.action; // a new action type still shows something useful
  }
}
