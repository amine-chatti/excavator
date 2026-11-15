import { AnimatePresence, motion } from "motion/react";
import { Quote } from "lucide-react";
import type { ExtractiveExplanationResponse } from "@/lib/api-types";
import { sortExtracts } from "@/lib/timeline";
import { quoteVariants } from "@/motion";

export function Unearthed({ data, selectedEvent }: { data: ExtractiveExplanationResponse; selectedEvent: string | null }) {
  const extracts = sortExtracts(data.extracts);
  return <section className="section-block unearthed" aria-labelledby="unearthed-title">
    <div className="section-heading"><span className="section-number">02</span><div><p className="eyebrow">Original source fragments</p><h2 id="unearthed-title">Unearthed</h2></div><span className="section-count">{extracts.length} ARTIFACT{extracts.length === 1 ? "" : "S"}</span></div>
    <p className="quote-note">Exact words from commits, pull requests, issues and reviews.</p>
    {data.status === "no_evidence" || !extracts.length ? <div className="empty-state evidence-empty"><Quote size={19} /><p>Nothing unearthed yet.</p><span>No written evidence found for this function in the analyzed sources.</span></div> : <div className="artifact-list"><AnimatePresence initial={false}>{extracts.map((extract, index) => {
      const linked = Boolean(selectedEvent && extract.lineage_event === selectedEvent);
      return <motion.article key={`${extract.source_kind}-${extract.reference}-${extract.created_at}-${index}`} className={`artifact ${selectedEvent ? (linked ? "quote-linked" : "quote-dimmed") : ""}`} variants={quoteVariants} initial="hidden" animate="visible" exit="exit" transition={{ delay: Math.min(index * 0.07, 0.28) }}>
      <header className="artifact-meta"><span className="quote-label">VERBATIM · {extract.source_kind.replace("_", " ")} {String(extract.reference)}</span><span className="artifact-ref">{extract.lineage_event ? `Tied to ${extract.lineage_event}` : "Not tied to a single event"}</span></header>
      <blockquote>{extract.excerpt}</blockquote>
    </motion.article>})}</AnimatePresence></div>}
  </section>;
}
