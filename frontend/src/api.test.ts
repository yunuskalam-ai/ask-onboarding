import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, changeTicketStatus, listTickets, setSignedOutHandler, uploadDocument } from "./api";

function mockFetch(status: number, body: unknown) {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  setSignedOutHandler(() => {});
});

describe("API errors", () => {
  it("a 401 signs the app out and throws", async () => {
    const signedOut = vi.fn();
    setSignedOutHandler(signedOut);
    mockFetch(401, { detail: "Please sign in." });

    await expect(listTickets()).rejects.toBeInstanceOf(ApiError);
    expect(signedOut).toHaveBeenCalledOnce();
  });

  it("a 403 shows the server's message and does not sign out", async () => {
    const signedOut = vi.fn();
    setSignedOutHandler(signedOut);
    mockFetch(403, { detail: "This needs the manager or admin role." });

    await expect(changeTicketStatus(1, "closed", "")).rejects.toThrow("This needs the manager or admin role.");
    expect(signedOut).not.toHaveBeenCalled();
  });

  it("an error without a JSON body still gives a readable message", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>Bad gateway</html>", { status: 502 })));
    await expect(listTickets()).rejects.toThrow("Request failed (502).");
  });

  it("an upload that is too large reports the server's limit", async () => {
    mockFetch(413, { detail: "Files can be at most 20 MB." });
    await expect(uploadDocument(new File(["x"], "big.pdf"))).rejects.toThrow("Files can be at most 20 MB.");
  });
});

describe("requests", () => {
  it("a status change is a PATCH with a JSON body", async () => {
    const fetchMock = mockFetch(200, { id: 7, status: "resolved" });
    await changeTicketStatus(7, "resolved", "Done.");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/tickets/7");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body as string)).toEqual({ status: "resolved", note: "Done." });
  });
});
