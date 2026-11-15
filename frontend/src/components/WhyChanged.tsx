import { motion } from "motion/react";
import { AlertTriangle, RotateCw, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ExplanationClaim } from "@/lib/api-types";
import { explanationSourceLabel } from "@/lib/story";
import { contentVariants } from "@/motion";

export type ExplanationPanelState =
  | { status: "loading" }
  | { status: "idle" }
  | { status: "busy" }
  | { status: "explained"; summary: string; claims: ExplanationClaim[] }
  | { status: "insufficient" }
  | { status: "error"; message: string; retryAction: "load" | "generate" };

interface Props {
  state: ExplanationPanelState;
  onGenerate: () => void;
  onRetry: () => void;
}

function EvidenceClaims({ claims }: { claims: ExplanationClaim[] }) {
  return <div className="claims-list">{claims.map((claim) => <article className="claim-block" key={claim.position}>
    <p className="claim-text">{claim.text}</p>
    {claim.quotes.map((quote, index) => <p className="claim-citation" key={`${quote.snippet_id}-${index}`}><span>Verified quote from {explanationSourceLabel(quote.source_type, quote.snippet_id)}:</span> <q>{quote.quote}</q></p>)}
  </article>)}</div>;
}

export function WhyChanged({ state, onGenerate, onRetry }: Props) {
  const generating = state.status === "busy";
  const retry = state.status === "error" ? onRetry : onGenerate;
  return <section className="section-block why-changed" aria-labelledby="why-changed-title">
    <div className="section-heading"><span className="section-number">03</span><div><p className="eyebrow">Model interpretation</p><h2 id="why-changed-title">Why it changed</h2></div></div>
    <p className="why-disclaimer">Written by a model, so it can be wrong. Every claim points to an exact quote that code has checked.</p>
    {state.status === "loading" ? <div className="why-state"><div className="why-copy"><p className="eyebrow">Checking the archive</p><h3>Looking for an explanation</h3></div></div> : state.status === "explained" ? <motion.div className="explanation-result" variants={contentVariants} initial="hidden" animate="visible">
      <div className="inference-stamp">{state.claims.flatMap((claim) => claim.quotes).find((quote) => quote.epistemic_label)?.epistemic_label ?? "inferred"}</div>
      <p className="inference-note">Written by a local model. The quotes are verified, the interpretation is the model’s.</p>
      <h3 className="explanation-summary">{state.summary}</h3>
      <EvidenceClaims claims={state.claims} />
      <Button variant="outline" className="explain-button" onClick={onGenerate}><RotateCw />Run again</Button>
    </motion.div> : state.status === "error" ? <div className="why-state error-state"><AlertTriangle className="state-icon" /><div className="why-copy"><h3>Could not load an explanation</h3><p>{state.message}</p><p className="plain-hint">Check that the backend is running and that Ollama is running if you use the local model.</p></div><Button variant="outline" className="explain-button" onClick={retry}><RotateCw />Retry</Button></div> : state.status === "insufficient" ? <div className="why-state"><Sparkles className="state-icon" /><div className="why-copy"><h3>Not enough evidence</h3><p>The model could not back any claim with an exact quote, so nothing is shown. Try again, or read the unearthed quotes above.</p></div><Button variant="outline" className="explain-button" onClick={onGenerate}>Try again</Button></div> : generating ? <div className="why-state busy-state" aria-live="polite"><Sparkles className="state-icon" /><div className="why-copy"><h3>Reading the quotes…</h3><p>The model is writing. Code will check every quote it cites.</p></div><Button variant="outline" className="explain-button" disabled>Writing…</Button></div> : <div className="why-state"><Sparkles className="state-icon" /><div className="why-copy"><h3>No explanation yet</h3><p>A model reads the quotes above and writes a short explanation. It runs on your PC, so it can take a minute.</p></div><Button className="explain-button" onClick={onGenerate}><Sparkles />Generate explanation</Button></div>}
  </section>;
}
