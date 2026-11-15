import { motion } from "motion/react";
import type { LineageResponse } from "@/lib/api-types";
import { makeTimeline, type MarkerShape, type TimelineKind } from "@/lib/timeline";
import { makeSymbolStory } from "@/lib/story";

const labels: Record<TimelineKind, string> = { added: "First seen", modified: "Body changed", renamed: "Renamed", moved: "Moved", removed: "Deleted", carried: "No body change" };
const eventKinds: Array<[TimelineKind, string]> = [["added", "First seen"], ["modified", "Body changed"], ["renamed", "Renamed"], ["moved", "Moved"], ["removed", "Deleted"]];

function Shape({ shape }: { shape: MarkerShape }) {
  return <span className={`event-shape ${shape}`} aria-hidden="true">{shape === "cross" ? "\u00d7" : ""}</span>;
}

function dateText(value: string) {
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function CrossSection({ data, selectedSha, onSelect, evidenceCount = 0 }: { data: LineageResponse; selectedSha: string | null; onSelect: (sha: string, kind: string) => void; evidenceCount?: number }) {
  const timeline = makeTimeline(data.versions, data.symbol.status);
  const story = makeSymbolStory(data.symbol.qualified_name, timeline.points, data.symbol.status);
  const versions = timeline.points.length;
  const derivedEvents = timeline.points.filter((point) => !point.baseline && point.kind !== "carried").length;
  const sourceCommits = new Set(timeline.points.map((point) => point.commitSha)).size;

  return <section className="section-block" aria-labelledby="cross-section-title">
    <header className="section-heading"><span className="section-number">01</span><div><p className="eyebrow">A symbol through time</p><h2 id="cross-section-title">Dig site</h2></div><span className="section-count">{versions} VERSIONS</span></header>
    <p className="timeline-story">{story}</p>
    <p className="timeline-explainer">Each entry represents a step in this function&apos;s history. Select an event to inspect its details and supporting evidence. One card is a version snapshot at a commit; its event label is derived by comparing neighboring versions.</p>
    <div className="history-stats" aria-label="Function history statistics">
      <article><strong>{versions}</strong><span>versions</span></article>
      <article><strong>{sourceCommits}</strong><span>source commits</span></article>
      <article><strong>{derivedEvents}</strong><span>derived events</span></article>
      <article><strong>{evidenceCount}</strong><span>written sources</span></article>
    </div>
    <div className="event-legend" aria-label="Event type legend">{eventKinds.map(([kind, label]) => <span className="event-legend-item" key={kind}><Shape shape={kind === "added" ? "circle" : kind === "modified" ? "square" : kind === "renamed" ? "diamond" : kind === "moved" ? "triangle" : "cross"} />{label}</span>)}</div>
    <details className="timeline-guide"><summary>How to read this timeline</summary><div className="timeline-guide-copy">
      <p>The commit is the source for each version snapshot. Event labels describe differences detected between adjacent snapshots.</p>
      <p>When adjacent versions have no detected difference, the entry is labeled &ldquo;No body change.&rdquo; The history is limited to the analyzed commit window.</p>
    </div></details>
    {!timeline.points.length ? <div className="empty-state timeline-empty"><p>No history found in this window.</p></div> : <div className="shaft-wrap">
      <span role="img" aria-label={`Timeline for ${data.symbol.qualified_name}`} className="sr-only" />
      {[...timeline.points].reverse().map((point, index) => {
        const sourceVersion = data.versions.find((version) => version.commit_sha === point.commitSha);
        const latest = index === 0;
        const eventLabel = point.baseline ? "Baseline" : labels[point.kind];
        const versionState = point.baseline
          ? `${latest ? (data.symbol.status === "deleted" ? "LAST VERSION" : "CURRENT VERSION") : "VERSION 01"} / WINDOW BASELINE`
          : latest ? (data.symbol.status === "deleted" ? "LAST VERSION" : "CURRENT VERSION") : `VERSION ${versions - index}`;
        const shape: MarkerShape = point.baseline ? "circle" : point.marker;
        return <motion.article layout key={point.commitSha} id={`event-${point.commitSha}`} className={`event-row ${point.baseline ? "baseline-row" : ""} ${selectedSha === point.commitSha ? "selected" : ""}`} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ type: "spring", stiffness: 260, damping: 25, delay: index * 0.035 }}>
          {!point.baseline && index < versions - 1 && <motion.span className="event-connector" initial={{ scaleY: 0 }} animate={{ scaleY: 1 }} transition={{ duration: 0.45, delay: index * 0.035 + 0.12 }} aria-hidden="true" />}
          <motion.button className={`event-node ${point.baseline ? "baseline" : ""} ${point.kind === "carried" ? "unchanged" : ""}`} onClick={() => onSelect(point.commitSha, point.kind)} aria-label={`Select ${eventLabel} at ${point.shortSha}`} initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 440, damping: 19, delay: index * 0.04 + 0.16 }}>{point.kind === "carried" ? <span className="event-mark-none" aria-hidden="true" /> : <Shape shape={shape} />}</motion.button>
          <article className="event-card">
            <button className="event-select" onClick={() => onSelect(point.commitSha, point.kind)} aria-pressed={selectedSha === point.commitSha}>
              <span className="event-card-top"><span className="event-type">{eventLabel}</span><span className="version-state">{versionState}</span></span>
              <h3>{point.commitMessage}</h3>
              <span className="event-meta"><time dateTime={point.authoredAt}>{dateText(point.authoredAt)}</time><code>{point.shortSha}</code><code>{point.path}:{sourceVersion?.start_line ?? "?"}</code></span>
            </button>
            <details className="event-details"><summary>Commit details</summary><div className="event-details-copy">
              <p><span>FULL SHA</span><code>{point.commitSha}</code></p>
              <p><span>PATH</span><code>{point.path}{sourceVersion?.start_line ? `:${sourceVersion.start_line}${sourceVersion.end_line ? `-${sourceVersion.end_line}` : ""}` : ""}</code></p>
              <p><span>PARSE</span><code>{sourceVersion?.parse_status ?? "unknown"}</code></p>
              <p><span>LINEAGE</span><code>{sourceVersion?.lineage_method ?? "unknown"}</code></p>
            </div></details>
            {point.baseline && <p className="baseline-copy">History window starts here. The function may have existed before the analyzed commits.</p>}
          </article>
        </motion.article>;
      })}
      <div className="shaft-direction"><span>NEWER <span aria-hidden="true">\u2191</span></span><span>OLDER <span aria-hidden="true">\u2193</span></span></div>
    </div>}
  </section>;
}
