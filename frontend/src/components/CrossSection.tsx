import { motion } from "motion/react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { LineageResponse } from "@/lib/api-types";
import { makeTimeline, type MarkerShape, type TimelineKind } from "@/lib/timeline";
import { motionTimings } from "@/motion";

const colors: Record<TimelineKind, string> = { added: "var(--moss)", modified: "var(--ochre)", renamed: "var(--rust)", moved: "var(--clay)", removed: "var(--bone-dim)", carried: "var(--ochre-dim)" };
function Marker({ shape, x, y }: { shape: MarkerShape; x: number; y: number }) {
  if (shape === "diamond") return <polygon points={`${x},${y - 8} ${x + 8},${y} ${x},${y + 8} ${x - 8},${y}`} />;
  if (shape === "triangle") return <polygon points={`${x},${y - 9} ${x + 9},${y + 7} ${x - 9},${y + 7}`} />;
  if (shape === "square") return <rect x={x - 7} y={y - 7} width="14" height="14" />;
  if (shape === "cross") return <path d={`M${x - 7} ${y - 7}l14 14m0-14l-14 14`} fill="none" stroke="currentColor" strokeWidth="3" />;
  return <circle cx={x} cy={y} r="7" />;
}

export function CrossSection({ data }: { data: LineageResponse }) {
  const timeline = makeTimeline(data.versions, data.symbol.status);
  const y = 111;
  return (
    <section className="section-block" aria-labelledby="cross-section-title">
      <div className="section-heading"><span className="section-number">01</span><div><p className="eyebrow">Stratigraphic record</p><h2 id="cross-section-title">Cross-section</h2></div><span className="section-count">{timeline.points.length} COMMIT{timeline.points.length === 1 ? "" : "S"}</span></div>
      {timeline.points.length ? <div className="timeline-frame"><div className="timeline-scroll"><TooltipProvider delayDuration={80}><svg className="timeline-svg" role="img" aria-label={`Timeline for ${data.symbol.qualified_name}`} viewBox={`0 0 ${timeline.width} ${timeline.height}`} width={timeline.width}>
        <defs><pattern id="strata-hatch" width="8" height="8" patternTransform="rotate(32)" patternUnits="userSpaceOnUse"><line x1="0" y1="0" x2="0" y2="8" stroke="rgba(255,246,221,.17)" strokeWidth="2" /></pattern><linearGradient id="baseline-fade"><stop offset="0" stopColor="var(--soil)" /><stop offset="1" stopColor="var(--soil)" stopOpacity="0" /></linearGradient></defs>
        {timeline.points.map((point, index) => <motion.line key={`tick-${point.commitSha}`} x1={point.x} x2={point.x} y1="36" y2="204" stroke="var(--rule)" strokeDasharray="2 5" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ ...motionTimings.quick, delay: index * 0.04 }} />)}
        {timeline.bands.map((band, index) => <motion.g key={band.id} style={{ transformOrigin: `${band.x}px ${y}px` }} initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ ...motionTimings.spring, delay: 0.14 + index * 0.07 }}>
          <path d={`M${band.x} ${y - 16} L${band.x + band.width - 12} ${y - 12} l12 8 -6 8 6 6 -12 13 H${band.x} Z`} fill={colors[band.kind]} opacity=".79" />
          <path d={`M${band.x} ${y - 16} L${band.x + band.width - 12} ${y - 12} l12 8 -6 8 6 6 -12 13 H${band.x} Z`} fill="url(#strata-hatch)" />
        </motion.g>)}
        {timeline.points.map((point, index) => <g key={point.commitSha} className="timeline-point">
          {point.baseline && <line x1={point.x} x2={point.x} y1={y - 19} y2={y + 21} stroke="var(--bone)" strokeWidth="2" strokeDasharray="3 4" />}
          <Tooltip><TooltipTrigger asChild><motion.g tabIndex={0} role="img" aria-label={`${point.shortSha} ${point.kind}`} style={{ color: colors[point.kind], fill: colors[point.kind] }} initial={{ scale: 0, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ ...motionTimings.marker, delay: 0.38 + index * 0.07 }}><circle cx={point.x} cy={y} r="13" fill="transparent" stroke="none" /><Marker shape={point.marker} x={point.x} y={y} /><circle cx={point.x} cy={y} r="3" fill="var(--soil)" /></motion.g></TooltipTrigger><TooltipContent className="timeline-tooltip"><strong>{point.shortSha}</strong><span>{new Date(point.authoredAt).toLocaleDateString()}</span><span>{point.kind}</span><small>{point.commitMessage}</small></TooltipContent></Tooltip>
          <text x={point.x} y="163" textAnchor="middle" className="timeline-sha">{point.shortSha}</text><text x={point.x} y="180" textAnchor="middle" className="timeline-date">{new Date(point.authoredAt).toLocaleDateString(undefined, { month: "short", year: "2-digit" })}</text>
        </g>)}
        <line x1="54" x2={timeline.width - 42} y1="205" y2="205" stroke="var(--rule-strong)" />
      </svg></TooltipProvider></div><motion.div className="timeline-legend" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3, delay: 0.65 }}>
        {([["added", "circle"], ["modified", "diamond"], ["renamed", "triangle"], ["moved", "square"], ["removed", "cross"]] as const).map(([event, shape]) => <span key={event} className="legend-item"><i className={`legend-shape ${shape}`} style={{ "--legend-color": colors[event] } as React.CSSProperties} />{event}</span>)}
        {timeline.points.some((point) => point.baseline) && <span className="baseline-note"><i /> history window starts here, real birth may be earlier</span>}
      </motion.div></div> : <div className="empty-state timeline-empty"><span>∅</span><p>No lineage strata in this window.</p></div>}
    </section>
  );
}
