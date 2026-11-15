import { AnimatePresence, motion } from "motion/react";
import { Quote } from "lucide-react";
import type { ExtractiveExplanationResponse } from "@/lib/api-types";
import { sortExtracts } from "@/lib/timeline";
import { quoteVariants } from "@/motion";

export function Unearthed({ data, selectedEvent, eventKindCounts, onSelectEvent }: { data: ExtractiveExplanationResponse; selectedEvent: string | null; eventKindCounts: Record<string, number>; onSelectEvent: (event: string) => void }) {
  const extracts = sortExtracts(data.extracts);
  return <section className="section-block unearthed" aria-labelledby="unearthed-title">
    <div className="section-heading"><span className="section-number">02</span><div><p className="eyebrow">Original source fragments</p><h2 id="unearthed-title">Unearthed</h2></div><span className="section-count">{extracts.length} SOURCES</span></div>
    <p className="quote-note">Original words from commits, pull requests, issues, and reviews.</p>
    {data.status === "no_evidence" || !extracts.length ? <div className="empty-state evidence-empty"><Quote size={19} /><p>Nothing unearthed yet.</p><span>No written evidence found for this function in the analyzed sources.</span></div> : <div className="artifact-list"><AnimatePresence initial={false}>{extracts.map((extract, index) => {
      const linked = Boolean(selectedEvent && extract.lineage_event === selectedEvent && eventKindCounts[extract.lineage_event] === 1);
      const sourceKind = extract.source_kind.replaceAll("_", " ");
      const tiedToSingleEvent = Boolean(extract.lineage_event && eventKindCounts[extract.lineage_event] === 1);
      return <motion.article key={`${extract.source_kind}-${extract.reference}-${extract.created_at}-${index}`} className={`artifact ${selectedEvent ? (linked ? "quote-linked" : "quote-dimmed") : ""}`} variants={quoteVariants} initial="hidden" animate="visible" exit="exit" transition={{ delay: Math.min(index * 0.07, 0.28) }}>
        <header className="artifact-meta"><span className="quote-label">VERBATIM &middot; {sourceKind}</span><span className="artifact-ref">Reference {String(extract.reference)}</span><time dateTime={extract.created_at}>{new Date(extract.created_at).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })}</time></header>
        <blockquote>{extract.excerpt}</blockquote>
        <footer className="artifact-footer">{tiedToSingleEvent ? <><span className="event-stamp">Linked to {extract.lineage_event}</span><button className="evidence-event-link" onClick={() => onSelectEvent(extract.lineage_event!)}>Show event &rarr;</button></> : <span className="unlinked-stamp">Not tied to a single event</span>}</footer>
      </motion.article>;
    })}</AnimatePresence></div>}
  </section>;
}
