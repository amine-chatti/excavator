import { motion } from "motion/react";
import { AlertTriangle, RotateCw, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import type { ExplanationClaim } from "@/lib/api-types";
import { explanationSourceLabel } from "@/lib/story";
import { contentVariants } from "@/motion";

export type ExplanationPanelState =
  | { status: "loading" } | { status: "idle" } | { status: "busy" }
  | { status: "explained"; summary: string; claims: ExplanationClaim[] }
  | { status: "insufficient" } | { status: "error"; message: string; retryAction: "load" | "generate" };
interface Props { state: ExplanationPanelState; onGenerate: () => void; onRetry: () => void; deleted?: boolean }

function EvidenceClaims({ claims }: { claims: ExplanationClaim[] }) {
  return <div className="claims-list">{claims.map((claim, index) => <motion.article className="claim-block" key={claim.position} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.18 }}>
    <p className="claim-text">{claim.text}</p>
    {claim.quotes.map((quote, quoteIndex) => <p className="claim-citation" key={`${quote.snippet_id}-${quoteIndex}`}><span>Verified quote from {explanationSourceLabel(quote.source_type, quote.snippet_id)}:</span><q>{quote.quote}</q></p>)}
  </motion.article>)}</div>;
}

export function WhyChanged({ state, onGenerate, onRetry, deleted = false }: Props) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (state.status !== "busy") { setElapsed(0); return; }
    const started = Date.now();
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 250);
    return () => window.clearInterval(timer);
  }, [state.status]);
  const retry = state.status === "error" ? onRetry : onGenerate;
  return <section className="section-block why-changed" aria-labelledby="why-changed-title">
    <div className="section-heading"><span className="section-number">02</span><div><p className="eyebrow">AI interpretation</p><h2 id="why-changed-title">Why it changed</h2></div></div>
    {deleted && <p className="deleted-notice">This function no longer exists.</p>}
    <p className="why-disclaimer">An interpretation, not a developer quote. Each claim needs an exact quote checked by code.</p>
    {state.status === "loading" ? <div className="why-state"><div className="why-copy"><h3>Checking for a saved explanation</h3></div></div>
      : state.status === "explained" ? <motion.div className="explanation-result" variants={contentVariants} initial="hidden" animate="visible">
        <div className="inference-stamp">INFERRED · AI interpretation</div><p className="explanation-summary">{state.summary}</p><EvidenceClaims claims={state.claims} />
        <Button variant="outline" className="explain-button" onClick={onGenerate}><RotateCw />Run again</Button>
      </motion.div>
      : state.status === "error" ? <div className="why-state error-state"><AlertTriangle className="state-icon" /><div className="why-copy"><h3>Could not generate an explanation</h3><p>{state.message}</p><p>Check that the backend is running and that Ollama is running if you use the local model.</p></div><Button variant="outline" className="explain-button" onClick={retry}><RotateCw />Retry</Button></div>
      : state.status === "insufficient" ? <div className="why-state"><Sparkles className="state-icon" /><div className="why-copy"><h3>Not enough evidence</h3><p>No claim could be backed with a checked quote. History and source evidence are still available above.</p></div><Button variant="outline" className="explain-button" onClick={onGenerate}>Try again</Button></div>
      : state.status === "busy" ? <div className="why-state busy-state" aria-live="polite"><Sparkles className="state-icon" /><div className="why-copy"><h3>Reading the quotes…</h3><p>Elapsed {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")}</p><div className="indeterminate-bar" /></div><Button variant="outline" className="explain-button" disabled>Writing…</Button></div>
      : <div className="why-state"><Sparkles className="state-icon" /><div className="why-copy"><h3>No explanation yet</h3><p>Ask AI to explain the change. Every claim must cite an exact quote verified by code.</p></div><Button className="explain-button" onClick={onGenerate}><Sparkles />Generate explanation</Button></div>}
  </section>;
}
