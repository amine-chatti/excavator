import { AnimatePresence, motion } from "motion/react";
import { Quote } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { ExtractiveExplanationResponse } from "@/lib/api-types";
import { sortExtracts } from "@/lib/timeline";
import { quoteVariants } from "@/motion";

export function Unearthed({ data }: { data: ExtractiveExplanationResponse }) {
  const extracts = sortExtracts(data.extracts);
  return <section className="section-block unearthed" aria-labelledby="unearthed-title">
    <div className="section-heading"><span className="section-number">02</span><div><p className="eyebrow">Original source fragments</p><h2 id="unearthed-title">Unearthed</h2></div><span className="section-count">{extracts.length} ARTIFACT{extracts.length === 1 ? "" : "S"}</span></div>
    <p className="quote-note">Quotes from the original sources. Not an interpretation.</p>
    {data.status === "no_evidence" || !extracts.length ? <div className="empty-state evidence-empty"><Quote size={19} /><p>Nothing unearthed yet.</p><span>There are no linked source excerpts for this specimen.</span></div> : <div className="artifact-list"><AnimatePresence initial={false}>{extracts.map((extract, index) => <motion.article key={`${extract.source_kind}-${extract.reference}-${extract.created_at}-${index}`} className="artifact" variants={quoteVariants} initial="hidden" animate="visible" exit="exit" transition={{ delay: Math.min(index * 0.07, 0.28) }}>
      <header className="artifact-meta"><Badge variant="outline" className="source-stamp">{extract.source_kind.replace("_", " ")}</Badge><span className="artifact-ref">{String(extract.reference)}</span>{extract.lineage_event && <Badge className="event-stamp">{extract.lineage_event}</Badge>}<time>{new Date(extract.created_at).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })}</time></header>
      <blockquote>{extract.excerpt}</blockquote>
      <span className="quote-label">VERIFIED QUOTE</span>
    </motion.article>)}</AnimatePresence></div>}
  </section>;
}
