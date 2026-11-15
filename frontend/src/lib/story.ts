import type { SymbolRecord } from "@/lib/api-types";
import type { TimelinePoint } from "@/lib/timeline";

function dateText(value: string): string {
  return new Date(value).toLocaleDateString("en", { year: "numeric", month: "long", day: "numeric", timeZone: "UTC" });
}

export function makeSymbolStory(name: string, points: readonly TimelinePoint[], status: SymbolRecord["status"]): string {
  const ordered = [...points].sort((left, right) => left.authoredAt.localeCompare(right.authoredAt) || left.commitSha.localeCompare(right.commitSha));
  const first = ordered[0];
  const removed = ordered.find((point) => point.kind === "removed");
  const bodyChanges = ordered.filter((point) => point.kind === "modified").length;
  const relocations = ordered.filter((point) => point.kind === "renamed" || point.kind === "moved").length;
  const sentences: string[] = [];

  if (first?.baseline) sentences.push(`${name} is already in the code at the start of this window.`);
  else if (first) sentences.push(`${name} first appears in commit ${first.shortSha} on ${dateText(first.authoredAt)}.`);
  if (bodyChanges) sentences.push(`Its body changed ${bodyChanges} ${bodyChanges === 1 ? "time" : "times"}.`);
  else sentences.push("Its body did not change.");
  if (relocations) sentences.push(`It was moved or renamed ${relocations} ${relocations === 1 ? "time" : "times"}.`);
  if (removed) sentences.push(`It was deleted in commit ${removed.shortSha}.`);
  else if (status === "exists") sentences.push("It still exists in the newest commit.");
  return sentences.join(" ");
}

export function explanationSourceLabel(sourceType: string, snippetId: string): string {
  const [prefix, reference] = snippetId.split(":");
  const kind = sourceType === "commit_message" ? "commit" : sourceType.replace("_", " ");
  return `${kind} ${reference || prefix || "source"}`;
}
