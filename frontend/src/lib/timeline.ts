import type {
  ExtractiveExtract,
  ExtractiveSourceKind,
  LineageEvent,
  LineageVersion,
  SymbolRecord,
} from "@/lib/api-types";

export type TimelineKind = LineageEvent | "carried";
export type MarkerShape = "circle" | "diamond" | "triangle" | "square" | "cross";

export interface TimelinePoint {
  commitSha: string;
  shortSha: string;
  authoredAt: string;
  commitMessage: string;
  path: string;
  qualifiedName: string;
  kind: TimelineKind;
  marker: MarkerShape;
  x: number;
  baseline: boolean;
}

export interface TimelineBand {
  id: string;
  x: number;
  width: number;
  kind: TimelineKind;
}

export interface TimelineModel {
  width: number;
  height: number;
  points: TimelinePoint[];
  bands: TimelineBand[];
}

const eventMarker: Record<TimelineKind, MarkerShape> = {
  added: "circle",
  modified: "square",
  renamed: "diamond",
  moved: "triangle",
  removed: "cross",
  carried: "circle",
};

export function sortLineageVersions(versions: readonly LineageVersion[]): LineageVersion[] {
  return [...versions].sort((left, right) => {
    const dateOrder = left.authored_at.localeCompare(right.authored_at);
    return dateOrder || left.commit_sha.localeCompare(right.commit_sha);
  });
}

function transitionKind(
  previous: LineageVersion | undefined,
  current: LineageVersion,
  isLast: boolean,
  status: SymbolRecord["status"],
): TimelineKind {
  if (status === "deleted" && isLast) return "removed";
  if (!previous) return "added";
  if (previous.path !== current.path) return "moved";
  if (previous.qualified_name !== current.qualified_name) return "renamed";
  if (previous.body_hash !== current.body_hash) return "modified";
  return "carried";
}

export function makeTimeline(
  versions: readonly LineageVersion[],
  status: SymbolRecord["status"],
): TimelineModel {
  const sorted = sortLineageVersions(versions);
  const width = Math.max(620, 172 + Math.max(0, sorted.length - 1) * 144);
  const height = 248;
  const startX = 76;
  const step = sorted.length > 1 ? (width - startX - 76) / (sorted.length - 1) : 0;
  const points = sorted.map((version, index): TimelinePoint => {
    const kind = transitionKind(sorted[index - 1], version, index === sorted.length - 1, status);
    return {
      commitSha: version.commit_sha,
      shortSha: version.commit_sha.slice(0, 7),
      authoredAt: version.authored_at,
      commitMessage: version.commit_message,
      path: version.path,
      qualifiedName: version.qualified_name,
      kind,
      marker: eventMarker[kind],
      x: startX + step * index,
      baseline: index === 0 && kind === "added",
    };
  });
  const bands = points.map((point, index): TimelineBand => {
    const nextX = points[index + 1]?.x;
    const bandWidth = nextX === undefined ? 92 : nextX - point.x;
    return {
      id: `${point.commitSha}-${index}`,
      x: point.x,
      width: bandWidth,
      kind: point.kind,
    };
  });
  return { width, height, points, bands };
}

const sourceOrder: Record<ExtractiveSourceKind, number> = {
  commit: 0,
  pull_request: 1,
  review_comment: 2,
  issue: 3,
};

export function sortExtracts(extracts: readonly ExtractiveExtract[]): ExtractiveExtract[] {
  return [...extracts].sort((left, right) => {
    const dateOrder = left.created_at.localeCompare(right.created_at);
    if (dateOrder) return dateOrder;
    const kindOrder = sourceOrder[left.source_kind] - sourceOrder[right.source_kind];
    if (kindOrder) return kindOrder;
    return String(left.reference).localeCompare(String(right.reference)) ||
      left.excerpt.localeCompare(right.excerpt);
  });
}

export function filterSymbols(
  symbols: readonly SymbolRecord[],
  query: string,
): SymbolRecord[] {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle) return [...symbols];
  return symbols.filter((symbol) =>
    [symbol.qualified_name, symbol.current_path ?? "", symbol.kind, symbol.status]
      .some((value) => value.toLocaleLowerCase().includes(needle)),
  );
}
