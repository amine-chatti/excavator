import { describe, expect, it } from "vitest";
import type { ExtractiveExtract, LineageVersion, SymbolRecord } from "@/lib/api-types";
import { filterSymbols, makeTimeline, sortExtracts, sortLineageVersions } from "@/lib/timeline";

const symbol: SymbolRecord = {
  id: 7,
  repository_id: 1,
  language: "python",
  kind: "function",
  qualified_name: "pkg.lookup",
  current_path: "src/lookup.py",
  status: "exists",
};

const version = (
  sha: string,
  authored_at: string,
  path: string,
  qualified_name: string,
  body_hash: string,
): LineageVersion => ({
  commit_sha: sha.repeat(40).slice(0, 40),
  commit_message: `Commit ${sha}`,
  authored_at,
  path,
  qualified_name,
  start_line: 1,
  end_line: 4,
  body_hash,
  parse_status: "ok",
  lineage_method: "exact",
});

const extracts: ExtractiveExtract[] = [
  {
    source_kind: "issue",
    reference: 3,
    excerpt: "later issue",
    lineage_event: null,
    created_at: "2026-03-01T00:00:00Z",
    label: "quote",
    epistemic_label: "verified",
  },
  {
    source_kind: "commit",
    reference: "abc1234",
    excerpt: "older commit",
    lineage_event: "added",
    created_at: "2026-01-01T00:00:00Z",
    label: "quote",
    epistemic_label: "verified",
  },
];

describe("timeline pure logic", () => {
  it("sorts versions oldest first with a stable SHA tie-break", () => {
    const left = version("b", "2026-01-01T00:00:00Z", "src/a.py", "pkg.a", "a");
    const right = version("a", "2026-01-01T00:00:00Z", "src/a.py", "pkg.a", "a");
    expect(sortLineageVersions([left, right]).map((item) => item.commit_sha[0])).toEqual([
      "a",
      "b",
    ]);
  });

  it("derives added, modified, renamed, moved, removed, and baseline markers", () => {
    const versions = [
      version("a", "2026-01-01T00:00:00Z", "src/a.py", "pkg.lookup", "one"),
      version("b", "2026-01-02T00:00:00Z", "src/a.py", "pkg.lookup", "two"),
      version("c", "2026-01-03T00:00:00Z", "src/a.py", "pkg.lookup_new", "three"),
      version("d", "2026-01-04T00:00:00Z", "src/new.py", "pkg.lookup_new", "three"),
      version("e", "2026-01-05T00:00:00Z", "src/new.py", "pkg.lookup_new", "three"),
    ];
    const timeline = makeTimeline(versions, "deleted");
    expect(timeline.points.map((point) => point.kind)).toEqual([
      "added",
      "modified",
      "renamed",
      "moved",
      "removed",
    ]);
    expect(timeline.points[0]?.baseline).toBe(true);
    expect(timeline.points.map((point) => point.marker)).toEqual([
      "circle",
      "diamond",
      "triangle",
      "square",
      "cross",
    ]);
    expect(timeline.bands).toHaveLength(5);
  });

  it("sorts extracts chronologically with source and reference tie-breaks", () => {
    expect(sortExtracts(extracts).map((item) => item.excerpt)).toEqual([
      "older commit",
      "later issue",
    ]);
  });

  it("filters symbols by qualified name, path, kind, or status", () => {
    const deleted = {
      ...symbol,
      id: 8,
      qualified_name: "pkg.old",
      current_path: "src/old.py",
      status: "deleted" as const,
    };
    expect(filterSymbols([symbol, deleted], "SRC/LOOKUP")).toEqual([symbol]);
    expect(filterSymbols([symbol, deleted], "deleted")).toEqual([deleted]);
    expect(filterSymbols([symbol, deleted], " ")).toEqual([symbol, deleted]);
  });
});
