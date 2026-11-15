import { motion } from "motion/react";
import { AlertTriangle, RotateCw, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import type { ExplanationClaim } from "@/lib/api-types";
import { explanationSourceLabel } from "@/lib/story";
import { contentVariants } from "@/motion";

export type ExplanationPanelState =
  | { status: "loading" } | { status: "idle" } | { status: "busy" }
  | { status: "demo-ready" } | { status: "demo-unavailable" }
  | { status: "explained"; summary: string; claims: ExplanationClaim[]; savedExample?: boolean }
  | { status: "insufficient"; savedExample?: boolean }
  | { status: "error"; message: string; retryAction: "load" | "generate" };
interface Props { state: ExplanationPanelState; onGenerate: () => void; onRetry: () => void; deleted?: boolean; demoMode?: boolean }

function EvidenceClaims({ claims }: { claims: ExplanationClaim[] }) {
  return <div className="claims-list">{claims.map((claim, index) => <motion.article className="claim-block" key={claim.position} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.18 }}>
    <p className="claim-text">{claim.text}</p>
    {claim.quotes.map((quote, quoteIndex) => <p className="claim-citation" key={`${quote.snippet_id}-${quoteIndex}`}><span>Verified quote from {explanationSourceLabel(quote.source_type, quote.snippet_id)}:</span><q>{quote.quote}</q></p>)}
  </motion.article>)}</div>;
}

export function WhyChanged({ state, onGenerate, onRetry, deleted = false, demoMode = false }: Props) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (state.status !== "busy") { setElapsed(0); return; }
    const started = Date.now();
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 250);
    return () => window.clearInterval(timer);
  }, [state.status]);
  const retry = state.status === "error" ? onRetry : onGenerate;
  return <section className="section-block why-changed" aria-labelledby="why-changed-title">
    <div className="section-heading"><span className="section-number">03</span><div><p className="eyebrow">AI interpretation</p><h2 id="why-changed-title">Why it changed</h2></div></div>
    {deleted && <p className="deleted-notice">This symbol no longer exists.</p>}
    <p className="why-disclaimer">An interpretation, not an original source. Each displayed claim includes its own quote checked by the backend.</p>
    {state.status === "loading" ? <div className="why-state"><div className="why-copy"><h3>Checking for a saved explanation</h3></div></div>
      : state.status === "explained" ? <motion.div className="explanation-result" variants={contentVariants} initial="hidden" animate="visible">
        <div className="inference-stamp">{state.savedExample ? "SAVED EXAMPLE · NOT LIVE" : "INFERRED · AI GENERATED"}</div><p className="explanation-summary">{state.summary}</p><EvidenceClaims claims={state.claims} />
        <Button variant="outline" className="explain-button" onClick={onGenerate}><RotateCw />{state.savedExample ? "Replay saved example" : "Run again"}</Button>
      </motion.div>
      : state.status === "error" ? <div className="why-state error-state"><AlertTriangle className="state-icon" /><div className="why-copy"><h3>Could not generate an explanation</h3><p>{state.message}</p><p>History and original evidence remain available. You can retry the explanation.</p></div><Button variant="outline" className="explain-button" onClick={retry}><RotateCw />Retry</Button></div>
      : state.status === "insufficient" ? <div className="why-state"><Sparkles className="state-icon" /><div className="why-copy"><h3>Not enough verified evidence</h3><p>No explanation is shown because there were no supported claims. The history and source quotes remain available.</p></div><Button variant="outline" className="explain-button" onClick={onGenerate}>{state.savedExample ? "Replay saved example" : "Try again"}</Button></div>
      : state.status === "demo-ready" ? <div className="why-state"><Sparkles className="state-icon" /><div className="why-copy"><h3>Saved AI example available</h3><p>Replay this saved explanation. Demo mode will not contact an AI service.</p></div><Button className="explain-button" onClick={onGenerate}><Sparkles />Replay saved example</Button></div>
      : state.status === "demo-unavailable" ? <div className="why-state"><Sparkles className="state-icon" /><div className="why-copy"><h3>No saved AI example</h3><p>To generate an AI explanation, run Excavator locally with an AI key.</p></div><Button variant="outline" className="explain-button" disabled>Local run required</Button></div>
      : state.status === "busy" ? <div className="why-state busy-state" aria-live="polite"><Sparkles className="state-icon" /><div className="why-copy"><h3>{demoMode ? "Replaying saved explanation" : "Generating interpretation"}</h3><p>Elapsed {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")} &middot; {demoMode ? "Showing a saved example. No live AI request is made." : "The backend handles this as one request and reports no internal progress."}</p><div className="indeterminate-bar" /></div><Button variant="outline" className="explain-button" disabled>In progress</Button></div>
      : <div className="why-state"><Sparkles className="state-icon" /><div className="why-copy"><h3>No explanation yet</h3><p>Ask AI to interpret the history. Every displayed claim will include an exact quote checked by the backend.</p></div><Button className="explain-button" onClick={onGenerate}><Sparkles />Generate explanation</Button></div>}
  </section>;
}
