import { describe, expect, it } from "vitest";
import type { TimelinePoint } from "@/lib/timeline";
import { makeSymbolStory } from "@/lib/story";

const point = (kind: TimelinePoint["kind"], options: Partial<TimelinePoint> = {}): TimelinePoint => ({
  commitSha: "1234567890abcdef", shortSha: "1234567", authoredAt: "2026-01-02T00:00:00Z",
  commitMessage: "Change symbol", path: "src/mod.py", qualifiedName: "pkg.mod", kind,
  marker: "circle", x: 76, baseline: false, ...options,
});

describe("plain-language symbol story", () => {
  it("describes an added symbol and plural body changes", () => {
    expect(makeSymbolStory("pkg.mod", [point("added"), point("modified", { shortSha: "7654321" }), point("modified", { shortSha: "abcdef0" })], "exists"))
      .toBe("pkg.mod first appears in commit 1234567 on January 2, 2026. Its body changed 2 times. It still exists in the newest commit.");
  });

  it("describes a baseline and singular body changes", () => {
    expect(makeSymbolStory("pkg.mod", [point("added", { baseline: true }), point("modified")], "exists"))
      .toBe("pkg.mod is already in the code at the start of this window. Its body changed 1 time. It still exists in the newest commit.");
  });

  it("describes a deleted symbol", () => {
    expect(makeSymbolStory("pkg.mod", [point("added", { baseline: true }), point("removed", { shortSha: "deadbee" })], "deleted"))
      .toBe("pkg.mod is already in the code at the start of this window. Its body did not change. It was deleted in commit deadbee.");
  });

  it("counts renames and moves together with singular wording", () => {
    expect(makeSymbolStory("pkg.mod", [point("renamed"), point("moved")], "exists"))
      .toBe("pkg.mod first appears in commit 1234567 on January 2, 2026. Its body did not change. It was moved or renamed 2 times. It still exists in the newest commit.");
    expect(makeSymbolStory("pkg.mod", [point("moved")], "exists"))
      .toContain("It was moved or renamed 1 time.");
    expect(makeSymbolStory("pkg.mod", [point("renamed")], "exists"))
      .toContain("It was moved or renamed 1 time.");
  });
});
