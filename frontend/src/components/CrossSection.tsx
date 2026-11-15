import { motion } from "motion/react";
import type { LineageResponse } from "@/lib/api-types";
import { makeTimeline, type MarkerShape, type TimelineKind } from "@/lib/timeline";
import { makeSymbolStory } from "@/lib/story";

const labels: Record<TimelineKind, string> = { added: "First seen", modified: "Body changed", renamed: "Renamed", moved: "Moved", removed: "Deleted", carried: "No body change" };
function Shape({ shape }: { shape: MarkerShape }) {
  return <span className={`event-shape ${shape}`} aria-hidden="true">{shape === "cross" ? "×" : ""}</span>;
}

export function CrossSection({ data, selectedSha, onSelect }: { data: LineageResponse; selectedSha: string | null; onSelect: (sha: string, kind: string) => void }) {
  const timeline = makeTimeline(data.versions, data.symbol.status);
  const story = makeSymbolStory(data.symbol.qualified_name, timeline.points, data.symbol.status);
  const height = Math.max(320, timeline.points.length * 144 + 50);
  const shaftX = 38;
  return <section className="section-block" aria-labelledby="cross-section-title">
    <header className="section-heading"><span className="section-number">01</span><div><p className="eyebrow">A function through time</p><h2 id="cross-section-title">Dig site</h2></div><span className="section-count">{timeline.points.length} COMMITS</span></header>
    <p className="timeline-story">{story}</p>
    {!timeline.points.length ? <div className="empty-state timeline-empty"><p>No history found in this window.</p></div> : <div className="shaft-wrap" style={{ minHeight: height }}>
      <svg className="shaft-svg" role="img" aria-label={`Timeline for ${data.symbol.qualified_name}`} viewBox={`0 0 76 ${height}`} preserveAspectRatio="none"><motion.path d={`M${shaftX} 0 V${height}`} pathLength={1} initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.25, ease: "easeOut" }} /></svg>
      {[...timeline.points].reverse().map((point, index) => {
        const top = 26 + index * 144;
        const label = point.baseline ? "Baseline" : labels[point.kind];
        return <motion.article key={point.commitSha} className={`event-row ${selectedSha === point.commitSha ? "selected" : ""}`} style={{ top }} initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} transition={{ type: "spring", stiffness: 260, damping: 25, delay: index * 0.045 }}>
      <motion.button className={`event-node ${point.baseline ? "baseline" : ""}`} style={{ top: 21 }} onClick={() => onSelect(point.commitSha, point.kind)} aria-label={`Select ${label} ${point.shortSha}`} initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 440, damping: 19, delay: index * .05 + .2 }}><Shape shape={point.marker} /></motion.button>
          <button className="event-card" onClick={() => onSelect(point.commitSha, point.kind)} aria-pressed={selectedSha === point.commitSha}>
            <div className="event-card-top"><span className="event-type">{label}</span><time>{new Date(point.authoredAt).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}</time></div>
            <h3>{point.commitMessage}</h3>
            <div className="event-meta"><code>{point.shortSha}</code><code>{point.path}:{data.versions.find((v) => v.commit_sha === point.commitSha)?.start_line ?? "?"}</code></div>
            {point.baseline && <p className="baseline-copy">History window starts here. The function may have existed before the analyzed commits.</p>}
          </button>
        </motion.article>;
      })}
      <div className="shaft-direction">NEWER ↑ <span>Digging down</span> OLDER ↓</div>
    </div>}
    <p className="timeline-story timeline-summary">{story}</p>
  </section>;
}
