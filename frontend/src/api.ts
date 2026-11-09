// Typed calls to the backend. In development Vite proxies /api to the API;
// in Docker, nginx does the same.

import { createSseParser } from "./sse";

export type DocumentStatus = "processing" | "ready" | "failed";

export type DocumentInfo = {
  id: number;
  filename: string;
  file_type: "pdf" | "md" | "txt";
  status: DocumentStatus;
  error: string | null;
  chunk_count: number;
  updated_at: string;
};

export type DocumentText = {
  id: number;
  filename: string;
  file_type: "pdf" | "md" | "txt";
  pages: { number: number | null; text: string }[];
};

export type Citation = {
  n: number;
  document_id: number;
  filename: string;
  page: number | null;
  start_char: number;
  end_char: number;
  text: string;
};

export type DoneReason = "answered" | "low_score" | "not_in_sources" | "refused";

export type ChatDone = { answered: boolean; reason: DoneReason; citations: Citation[] };

export type Turn = { role: "user" | "assistant"; content: string };

// Must match NO_ANSWER in backend/app/chat/prompt.py.
export const NO_ANSWER = "I couldn't find this in the company documents.";

export class ApiError extends Error {}

export type Role = "employee" | "manager" | "admin";

export type User = { id: number; email: string; name: string; role: Role };

// Called when the server says the session is gone (401), so the app can
// return to the sign-in page. The AuthProvider sets it.
let onSignedOut: () => void = () => {};
export function setSignedOutHandler(handler: () => void) {
  onSignedOut = handler;
}

/** fetch, plus: a 401 means signed out, and other errors become ApiError with the server's message. */
async function call(url: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(url, init);
  if (response.status === 401) {
    onSignedOut();
    throw new ApiError("Please sign in.");
  }
  if (!response.ok) throw new ApiError(await errorMessage(response));
  return response;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // not JSON: fall through
  }
  return `Request failed (${response.status}).`;
}

async function getJson<T>(url: string): Promise<T> {
  return (await call(url)).json();
}

function sendJson<T>(method: "POST" | "PATCH", url: string, body: unknown): Promise<T> {
  return call(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(
    (r) => (r.status === 204 ? (undefined as T) : r.json()),
  );
}

// --- Signing in --------------------------------------------------------------

/** The signed-in user, or null. */
export async function getMe(): Promise<User | null> {
  const response = await fetch("/api/auth/me");
  if (response.status === 401) return null;
  if (!response.ok) throw new ApiError(await errorMessage(response));
  return response.json();
}

export const listAccounts = () => getJson<User[]>("/api/auth/accounts");

export const signIn = (email: string) => sendJson<User>("POST", "/api/auth/sign-in", { email });

export const signOut = () => sendJson<void>("POST", "/api/auth/sign-out", {});

// --- People (admins) ------------------------------------------------------------

export const listUsers = () => getJson<User[]>("/api/users");

export const changeRole = (id: number, role: Role) => sendJson<User>("PATCH", `/api/users/${id}`, { role });

// --- Documents -------------------------------------------------------------------

export const listDocuments = () => getJson<DocumentInfo[]>("/api/documents");

export const getDocumentText = (id: number) => getJson<DocumentText>(`/api/documents/${id}`);

export const documentFileUrl = (id: number, page?: number | null) =>
  `/api/documents/${id}/file${page ? `#page=${page}` : ""}`;

export async function uploadDocument(file: File): Promise<void> {
  const form = new FormData();
  form.append("file", file);
  await call("/api/documents", { method: "POST", body: form });
}

export type ChatHandlers = {
  onToken: (text: string) => void;
  onDone: (done: ChatDone) => void;
  onError: (message: string) => void;
};

/** POST a question and call the handlers as the answer streams in. */
export async function streamChat(
  question: string,
  history: Turn[],
  handlers: ChatHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let finished = false;
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history }),
      signal,
    });
    if (response.status === 401) {
      onSignedOut();
      handlers.onError("Your session ended. Please sign in again.");
      return;
    }
    if (!response.ok || !response.body) {
      handlers.onError(await errorMessage(response));
      return;
    }

    const feed = createSseParser(({ event, data }) => {
      const payload = JSON.parse(data);
      if (event === "token") handlers.onToken(payload.text);
      else if (event === "done") {
        finished = true;
        handlers.onDone(payload);
      } else if (event === "error") {
        finished = true;
        handlers.onError(payload.message);
      }
    });

    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      feed(value);
    }
    if (!finished) handlers.onError("The answer was cut off. Please try again.");
  } catch (err) {
    if (signal?.aborted) return;
    handlers.onError("Could not reach the server. Is it running?");
    console.error(err);
  }
}

export type TicketDraft = { title: string; summary: string; drafted_by: "model" | "fallback" };

export type TicketStatus = "open" | "in_progress" | "resolved" | "closed";

export type TicketEvent = { at: string; user_name: string; from_status: TicketStatus; to_status: TicketStatus; note: string };

export type Ticket = {
  id: number;
  title: string;
  question: string;
  summary: string;
  user_name: string;
  status: TicketStatus;
  created_at: string;
  updated_at: string;
  history: TicketEvent[]; // oldest first
};

/** The model drafts a ticket through its create_ticket tool. Nothing is saved yet. */
export const draftTicket = (question: string) => sendJson<TicketDraft>("POST", "/api/tickets/draft", { question });

/** Saved as the signed-in user's ticket. */
export const createTicket = (ticket: { title: string; question: string; summary: string }) =>
  sendJson<Ticket>("POST", "/api/tickets", ticket);

export const listTickets = () => getJson<Ticket[]>("/api/tickets");

/** Managers and admins: move a ticket to a new status, with an optional note the employee sees. */
export const changeTicketStatus = (id: number, status: TicketStatus, note: string) =>
  sendJson<Ticket>("PATCH", `/api/tickets/${id}`, { status, note });
