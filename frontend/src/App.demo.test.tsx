import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "@/App";

const repository = {
  id: 1,
  owner: "pallets",
  name: "click",
  default_branch: null,
  indexing_status: "pending",
  head_sha_indexed: null,
  created_at: "2026-11-15T15:45:36.296651Z",
  updated_at: "2026-11-15T15:45:36.296651Z",
};
const symbols = {
  items: [{ id: 1, repository_id: 1, language: "python", kind: "function", qualified_name: "click.format_filename", current_path: "src/click/utils.py", status: "exists" }],
  total: 1,
};
const lineage = {
  symbol: symbols.items[0],
  versions: [{ commit_sha: "a".repeat(40), commit_message: "Add format_filename", authored_at: "2026-11-15T15:45:36.296651Z", path: "src/click/utils.py", qualified_name: "click.format_filename", start_line: 1, end_line: 2, body_hash: "b".repeat(64), parse_status: "ok", lineage_method: "exact" }],
};
const extractive = { status: "no_evidence", extracts: [] };
const explanation = {
  status: "explained",
  summary: "A saved explanation for this sample.",
  claims: [{ position: 0, text: "The helper keeps filename formatting consistent.", quotes: [{ snippet_id: "commit:abcdef0", source_type: "commit_message", quote: "keep filename formatting consistent", level: "mentioned", epistemic_label: "inferred" }] }],
};

function jsonResponse(value: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } }));
}

function demoFetch(withExplanation: boolean) {
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = new URL(String(input), "http://localhost").pathname;
    const method = init?.method ?? "GET";
    if (path === "/demo-data/repositories.json") return jsonResponse([repository]);
    if (path === "/demo-data/ai-symbols.json") return jsonResponse(withExplanation ? [1] : []);
    if (path === "/demo-data/repositories/1/symbols.json") return jsonResponse(symbols);
    if (path === "/demo-data/symbols/1/lineage.json") return jsonResponse(lineage);
    if (path === "/demo-data/symbols/1/extractive-explanation.json") return jsonResponse(extractive);
    if (path === "/demo-data/symbols/1/explanation.json") {
      return withExplanation ? jsonResponse(explanation) : jsonResponse({ detail: "Not Found" }, 404);
    }
    if (path.endsWith("/explain") && method === "POST") throw new Error("Demo mode must not post to the AI endpoint.");
    throw new Error(`Unexpected demo request: ${path}`);
  });
}
const symbolRow = async () => (await screen.findAllByRole("button", { name: /click\.format_filename/ })).find((el) => el.classList.contains("specimen-row"))!;
describe("saved-data demo mode", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("reads local fixtures and replays a saved explanation without calling the backend", async () => {
    vi.stubEnv("VITE_DEMO_MODE", "true");
    const fetchMock = demoFetch(true);
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    expect(await screen.findByText("SAMPLE DATA")).toBeTruthy();
    const firstSymbol = await symbolRow();
    fireEvent.click(firstSymbol);
    fireEvent.click(await screen.findByRole("button", { name: "Replay saved example" }));
    expect(await screen.findByRole("heading", { name: "Replaying saved explanation" })).toBeTruthy();
    expect(await screen.findByText("A saved explanation for this sample.")).toBeTruthy();
    expect(screen.getByText("SAVED EXAMPLE · NOT LIVE")).toBeTruthy();
    await waitFor(() => expect(fetchMock.mock.calls.every(([url]) => String(url).startsWith("/demo-data/"))).toBe(true));
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });

  it("explains that an AI key and local run are needed when no saved explanation exists", async () => {
    vi.stubEnv("VITE_DEMO_MODE", "true");
    vi.stubGlobal("fetch", demoFetch(false));
    render(<App />);
    fireEvent.click(await symbolRow());
    expect(await screen.findByRole("heading", { name: "AI examples are saved for a few functions" })).toBeTruthy();
    expect(screen.getByText("This function has no saved explanation. Functions marked AI in the list do. Generating new ones needs a local run with an AI key.")).toBeTruthy();
  });
});
