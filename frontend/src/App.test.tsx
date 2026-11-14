import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";

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
function routeFetch(options: { empty?: boolean; failLineage?: boolean } = {}) {
  return vi.fn((input: RequestInfo | URL) => {
    const path = String(input);
    if (path.endsWith("/repositories")) return response([repository]);
    if (path.includes("/symbols/") && path.endsWith("/lineage")) return options.failLineage ? response({ detail: "failure" }, 503) : response(lineage(Number(path.match(/symbols\/(\d+)/)?.[1])));
    if (path.endsWith("/extractive-explanation")) return response(options.empty ? { status: "no_evidence", extracts: [] } : { status: "extracts", extracts: [extract] });
    if (path.endsWith("/symbols")) return response(symbols);
    throw new Error(`Unexpected request ${path}`);
  });
}

describe("field notebook", () => {
  beforeEach(() => { vi.stubGlobal("fetch", routeFetch()); });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("loads repositories, selects another symbol, and shows timeline and source extracts", async () => {
    const fetchMock = routeFetch(); vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    await screen.findByRole("heading", { name: "pkg.first" });
    expect(await screen.findByRole("img", { name: "Timeline for pkg.first" })).toBeTruthy();
    expect(screen.getByText("This is the verbatim origin sentence.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /pkg\.Second/ }));
    expect(await screen.findByRole("heading", { name: "pkg.Second" })).toBeTruthy();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/symbols/12/extractive-explanation"), expect.anything()));
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/explain"))).toBe(false);
  });

  it("shows a designed empty state when there is no extractive evidence", async () => {
    vi.stubGlobal("fetch", routeFetch({ empty: true }));
    render(<App />);
    expect(await screen.findByText("Nothing unearthed yet.")).toBeTruthy();
  });

  it("shows a retryable error when a detail endpoint fails", async () => {
    vi.stubGlobal("fetch", routeFetch({ failLineage: true }));
    render(<App />);
    expect(await screen.findByText("The field server returned 503.")).toBeTruthy();
    expect(screen.getByRole("button", { name: /retry record/i })).toBeTruthy();
  });
});
