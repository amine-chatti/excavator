import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import type { ExplainResponse } from "@/lib/api-types";

const repository = { id: 1, owner: "field", name: "archive", default_branch: "main", indexing_status: "ready", head_sha_indexed: "abc", created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" };
const symbols = { items: [
  { id: 11, repository_id: 1, language: "python", kind: "function", qualified_name: "pkg.first", current_path: "src/pkg.py", status: "exists" },
  { id: 12, repository_id: 1, language: "python", kind: "class", qualified_name: "pkg.Second", current_path: "src/pkg.py", status: "exists" },
], total: 2 };
const lineage = (id: number) => ({ symbol: symbols.items.find((item) => item.id === id), versions: [
  { commit_sha: "abcdef0123456789", commit_message: "Add field specimen", authored_at: "2026-01-02T00:00:00Z", path: "src/pkg.py", qualified_name: id === 11 ? "pkg.first" : "pkg.Second", start_line: 1, end_line: 4, body_hash: "hash", parse_status: "ok", lineage_method: "exact" },
] });
const extract = { source_kind: "commit", reference: "abcdef0", excerpt: "This is the verbatim origin sentence.", lineage_event: "added", created_at: "2026-01-02T00:00:00Z", label: "quote", epistemic_label: "verified" };

function response(body: unknown, status = 200) { return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })); }
const explanation: ExplainResponse = {
  status: "explained", summary: "The function avoids repeated work.", dropped_claim_count: 0,
  truncated: false, truncated_snippet_count: 0, omitted_snippet_count: 0,
  claims: [{ position: 0, text: "It reduces repeated work.", quotes: [{ snippet_id: "commit:333c28d:message", source_type: "commit_message", quote: "reduces repeated work", level: "mentioned", epistemic_label: "inferred" }] }],
};
const insufficient: ExplainResponse = { status: "insufficient_evidence", summary: null, claims: [], dropped_claim_count: 1, truncated: false, truncated_snippet_count: 0, omitted_snippet_count: 0 };
function routeFetch(options: { empty?: boolean; failLineage?: boolean; post?: (id: number) => Promise<Response> } = {}) {
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    const method = init?.method ?? "GET";
    if (path.endsWith("/repositories")) return response([repository]);
    if (path.includes("/symbols/") && path.endsWith("/lineage")) return options.failLineage ? response({ detail: "failure" }, 503) : response(lineage(Number(path.match(/symbols\/(\d+)/)?.[1])));
    if (path.endsWith("/extractive-explanation")) return response(options.empty ? { status: "no_evidence", extracts: [] } : { status: "extracts", extracts: [extract] });
    if (path.endsWith("/explanation")) return response({ detail: "explanation not found" }, 404);
    if (path.endsWith("/explain") && method === "POST") return options.post?.(Number(path.match(/symbols\/(\d+)/)?.[1])) ?? response(explanation);
    if (path.endsWith("/symbols")) return response(symbols);
    throw new Error(`Unexpected request ${path}`);
  });
}

async function digIntoFirstSymbol() {
  const button = await screen.findByRole("button", { name: /^Dig into format_filename/ });
  await waitFor(() => expect(button).not.toHaveProperty("disabled", true));
  fireEvent.click(button);
}

describe("field notebook", () => {
  beforeEach(() => { vi.stubGlobal("fetch", routeFetch()); });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("loads repositories, selects another symbol, and shows timeline and source extracts", async () => {
    const fetchMock = routeFetch(); vi.stubGlobal("fetch", fetchMock);
    render(<App />); await digIntoFirstSymbol();
    await screen.findByRole("heading", { name: "pkg.first" });
    expect(await screen.findByRole("heading", { name: "No explanation yet" })).toBeTruthy();
    expect(await screen.findByRole("img", { name: "Timeline for pkg.first" })).toBeTruthy();
    expect(screen.getByText("This is the verbatim origin sentence.")).toBeTruthy();
    const secondSymbol = screen.getByRole("button", { name: /pkg\.Second/ });
    fireEvent.click(secondSymbol);
    await waitFor(() => expect(secondSymbol.className).toContain("is-selected"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/symbols/12/extractive-explanation"), expect.anything()));
    expect(fetchMock.mock.calls.some(([url, init]) => String(url).endsWith("/explanation") && (init?.method ?? "GET") === "GET")).toBe(true);
    expect(fetchMock.mock.calls.some(([url, init]) => String(url).endsWith("/explain") && init?.method === "POST")).toBe(false);
  });

  it("shows a designed empty state when there is no extractive evidence", async () => {
    vi.stubGlobal("fetch", routeFetch({ empty: true }));
    render(<App />); await digIntoFirstSymbol();
    expect(await screen.findByText("Nothing unearthed yet.")).toBeTruthy();
  });

  it("shows a retryable error when a detail endpoint fails", async () => {
    vi.stubGlobal("fetch", routeFetch({ failLineage: true }));
    render(<App />); await digIntoFirstSymbol();
    expect(await screen.findByText("failure")).toBeTruthy();
    expect(screen.getByRole("button", { name: /retry record/i })).toBeTruthy();
  });

  it("shows busy and explained states after a user starts generation", async () => {
    let resolvePost!: (value: Response) => void;
    const pending = new Promise<Response>((resolve) => { resolvePost = resolve; });
    vi.stubGlobal("fetch", routeFetch({ post: () => pending }));
    render(<App />); await digIntoFirstSymbol();
    fireEvent.click(await screen.findByRole("button", { name: "Generate explanation" }));
    expect(await screen.findByRole("heading", { name: "Generating interpretation" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "In progress" })).toHaveProperty("disabled", true);
    resolvePost(await response(explanation));
    expect(await screen.findByText("The function avoids repeated work.")).toBeTruthy();
    expect(screen.getByText("Verified quote from commit 333c28d:")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Run again" })).toBeTruthy();
  });

  it("shows insufficient evidence without displaying generated claims", async () => {
    vi.stubGlobal("fetch", routeFetch({ post: () => response(insufficient) }));
    render(<App />); await digIntoFirstSymbol();
    fireEvent.click(await screen.findByRole("button", { name: "Generate explanation" }));
    expect(await screen.findByRole("heading", { name: "Not enough verified evidence" })).toBeTruthy();
    expect(screen.queryByText("The function avoids repeated work.")).toBeNull();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });

  it("shows a server error and retries the explicit generation request", async () => {
    let attempts = 0;
    vi.stubGlobal("fetch", routeFetch({ post: () => ++attempts === 1 ? response({ detail: "local model unavailable" }, 502) : response(explanation) }));
    render(<App />); await digIntoFirstSymbol();
    fireEvent.click(await screen.findByRole("button", { name: "Generate explanation" }));
    expect(await screen.findByText("local model unavailable")).toBeTruthy();
    expect(screen.getByText("History and original evidence remain available. You can retry the explanation.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("The function avoids repeated work.")).toBeTruthy();
  });

  it("keeps explanation results keyed by symbol while generation finishes in the background", async () => {
    let resolvePost!: (value: Response) => void;
    const pending = new Promise<Response>((resolve) => { resolvePost = resolve; });
    vi.stubGlobal("fetch", routeFetch({ post: () => pending }));
    render(<App />); await digIntoFirstSymbol();
    fireEvent.click(await screen.findByRole("button", { name: "Generate explanation" }));
    const secondSymbol = screen.getByRole("button", { name: /pkg\.Second/ });
    fireEvent.click(secondSymbol);
    await waitFor(() => expect(secondSymbol.className).toContain("is-selected"));
    await screen.findByRole("heading", { name: "No explanation yet" });
    expect(screen.queryByText("The function avoids repeated work.")).toBeNull();
    resolvePost(await response(explanation));
    fireEvent.click(screen.getByRole("button", { name: /pkg\.first/ }));
    expect(await screen.findByText("The function avoids repeated work.")).toBeTruthy();
  });
});
