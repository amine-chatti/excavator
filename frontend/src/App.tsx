import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { AlertTriangle, RotateCw, Pickaxe } from "lucide-react";
import { FieldIndex } from "@/components/FieldIndex";
import { CrossSection } from "@/components/CrossSection";
import { Unearthed } from "@/components/Unearthed";
import { WhyChanged, type ExplanationPanelState } from "@/components/WhyChanged";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ApiError, getExtractiveExplanation, getLineage, getStoredExplanation, listRepositories, listSymbols, postExplanation } from "@/lib/api";
import type { ExtractiveExplanationResponse, LineageResponse, RepositoryRecord, SymbolRecord } from "@/lib/api-types";
import { contentVariants, mainVariants, selectionTransition } from "@/motion";
import { MotionConfig } from "motion/react";

function message(error: unknown) {
  return error instanceof ApiError ? error.message : "The archive could not be read.";
}

export default function App() {
  const [repositories, setRepositories] = useState<RepositoryRecord[]>([]);
  const [repositoryId, setRepositoryId] = useState<number | null>(null);
  const [symbols, setSymbols] = useState<SymbolRecord[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<{ sha: string; kind: string } | null>(null);
  const [query, setQuery] = useState("");
  const [motionOn, setMotionOn] = useState(() => {
    const saved = localStorage.getItem("excavator-motion");
    return saved === null ? !window.matchMedia("(prefers-reduced-motion: reduce)").matches : saved === "on";
  });
  const toggleMotion = (enabled: boolean) => {
    setMotionOn(enabled);
    localStorage.setItem("excavator-motion", enabled ? "on" : "off");
  };
  const [repositoryLoading, setRepositoryLoading] = useState(true);
  const [symbolsLoading, setSymbolsLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [repositoryError, setRepositoryError] = useState<string | null>(null);
  const [symbolsError, setSymbolsError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [lineage, setLineage] = useState<LineageResponse | null>(null);
  const [extractive, setExtractive] = useState<ExtractiveExplanationResponse | null>(null);
  const [explanationBySymbol, setExplanationBySymbol] = useState<Record<number, ExplanationPanelState>>({});
  const explanationLoads = useRef(new Set<number>());

  const loadRepositories = useCallback(async () => {
    setRepositoryLoading(true); setRepositoryError(null);
    try { const data = await listRepositories(); setRepositories(data); setRepositoryId((current) => current && data.some((repo) => repo.id === current) ? current : data[0]?.id ?? null); }
    catch (error) { setRepositoryError(message(error)); }
    finally { setRepositoryLoading(false); }
  }, []);
  useEffect(() => { void loadRepositories(); }, [loadRepositories]);

  const loadSymbols = useCallback(async (id: number) => {
    setSymbolsLoading(true); setSymbolsError(null); setSymbols([]); setSelectedId(null); setSelectedEvent(null); setLineage(null); setExtractive(null); setDetailError(null);
    try { const data = await listSymbols(id); setSymbols(data.items); setSelectedId(null); }
    catch (error) { setSymbolsError(message(error)); }
    finally { setSymbolsLoading(false); }
  }, []);
  useEffect(() => { if (repositoryId !== null) void loadSymbols(repositoryId); else { setSymbols([]); setSelectedId(null); setSymbolsLoading(false); } }, [repositoryId, loadSymbols]);

  const loadDetails = useCallback(async (id: number) => {
    setDetailLoading(true); setDetailError(null); setLineage(null); setExtractive(null);
    try { const [history, evidence] = await Promise.all([getLineage(id), getExtractiveExplanation(id)]); setLineage(history); setExtractive(evidence); }
    catch (error) { setDetailError(message(error)); }
    finally { setDetailLoading(false); }
  }, []);
  useEffect(() => { if (selectedId !== null) void loadDetails(selectedId); }, [selectedId, loadDetails]);

  const loadExplanation = useCallback((id: number, retry = false) => {
    if (explanationLoads.current.has(id) || (!retry && explanationBySymbol[id])) return;
    explanationLoads.current.add(id);
    setExplanationBySymbol((current) => ({ ...current, [id]: { status: "loading" } }));
    void getStoredExplanation(id).then((saved) => {
      setExplanationBySymbol((current) => ({
        ...current,
        [id]: saved
          ? { status: "explained", summary: saved.summary, claims: saved.claims }
          : { status: "idle" },
      }));
    }).catch((error: unknown) => {
      setExplanationBySymbol((current) => ({
        ...current,
        [id]: { status: "error", message: message(error), retryAction: "load" },
      }));
    }).finally(() => explanationLoads.current.delete(id));
  }, [explanationBySymbol]);
  useEffect(() => {
    if (selectedId !== null) loadExplanation(selectedId);
  }, [selectedId, loadExplanation]);

  const generateExplanation = useCallback(async (id: number) => {
    setExplanationBySymbol((current) => ({ ...current, [id]: { status: "busy" } }));
    try {
      const result = await postExplanation(id);
      setExplanationBySymbol((current) => ({
        ...current,
        [id]: result.status === "explained" && result.summary !== null
          ? { status: "explained", summary: result.summary, claims: result.claims }
          : { status: "insufficient" },
      }));
    } catch (error) {
      setExplanationBySymbol((current) => ({
        ...current,
        [id]: { status: "error", message: message(error), retryAction: "generate" },
      }));
    }
  }, []);

  const retryDetails = () => { if (selectedId !== null) void loadDetails(selectedId); };
  const activeSymbol = symbols.find((item) => item.id === selectedId) ?? null;
  const activeExplanation = selectedId === null ? undefined : explanationBySymbol[selectedId];
  return <MotionConfig reducedMotion={motionOn ? "never" : "user"}><TooltipProvider>
    <div className={`app-shell ${motionOn ? "" : "motion-disabled"}`}>
      <FieldIndex repositories={repositories} repositoryId={repositoryId} onRepositoryChange={setRepositoryId} symbols={symbols} selectedId={selectedId} onSelectSymbol={(id) => { setSelectedId(id); setSelectedEvent(null); }} query={query} onQueryChange={setQuery} loading={repositoryLoading || symbolsLoading} error={repositoryError ?? symbolsError} onRetry={() => repositoryError ? void loadRepositories() : repositoryId !== null && void loadSymbols(repositoryId)} motionOn={motionOn} onMotionChange={toggleMotion} />
      <motion.main className="field-main" variants={mainVariants} initial="hidden" animate="visible">
        <header className="main-topline"><span>FIELD NOTE <b>№ 001</b></span><span>SYMBOL ARCHIVE <i>·</i> PYTHON LINEAGE</span></header>
        <AnimatePresence mode="wait">
          {repositoryLoading ? <motion.div key="loading" className="detail-loading" variants={contentVariants} initial="hidden" animate="visible" exit={{ opacity: 0 }}><Skeleton className="h-5 w-44" /><Skeleton className="h-16 w-2/3" /><Skeleton className="h-64 w-full" /></motion.div> : repositoryError || symbolsError ? <motion.div key="error" className="state-panel" initial={{ opacity: 0 }} animate={{ opacity: 1 }}><AlertTriangle /><p>{repositoryError ?? symbolsError}</p><Button variant="outline" onClick={() => repositoryError ? void loadRepositories() : repositoryId !== null && void loadSymbols(repositoryId)}><RotateCw />Retry</Button></motion.div> : !repositories.length ? <motion.div key="no-repositories" className="state-panel" initial={{ opacity: 0 }} animate={{ opacity: 1 }}><Pickaxe /><h1>No field sites yet</h1><p>Index a repository to begin tracing its symbols through time.</p></motion.div> : !symbolsLoading && !symbols.length ? <motion.div key="no-symbols" className="state-panel" initial={{ opacity: 0 }} animate={{ opacity: 1 }}><Pickaxe /><h1>No specimens found</h1><p>This repository has no indexed symbols to inspect.</p></motion.div> : activeSymbol ? <motion.div key={activeSymbol.id} className="specimen-detail" initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -8 }} transition={selectionTransition}>
            <div className="specimen-title"><p className="eyebrow">Specimen <span>/{activeSymbol.kind}</span></p><h1><motion.span layoutId={`symbol-title-${activeSymbol.id}`}>{activeSymbol.qualified_name}</motion.span></h1><div className="title-meta"><span>{activeSymbol.current_path ?? "path not recorded"}</span><span className={`status-tag ${activeSymbol.status}`}>{activeSymbol.status}</span><span>SYMBOL ID {String(activeSymbol.id).padStart(4, "0")}</span></div></div>
            {detailLoading ? <div className="detail-loading"><Skeleton className="h-5 w-44" /><Skeleton className="h-60 w-full" /><Skeleton className="h-28 w-full" /></div> : detailError ? <div className="state-panel detail-error"><AlertTriangle /><p>{detailError}</p><Button variant="outline" onClick={retryDetails}><RotateCw />Retry record</Button></div> : lineage && extractive ? <div className="detail-content"><CrossSection data={lineage} selectedSha={selectedEvent?.sha ?? null} onSelect={(sha, kind) => setSelectedEvent({ sha, kind })} /></div> : null}
          </motion.div> : <motion.section key="intro" className="intro-screen" initial="hidden" animate="visible" exit={{ opacity: 0 }}>
            <p className="intro-kicker">A CODE ARCHAEOLOGY TOOL</p>
            <motion.h1>{"Why does this code look like this?".split(" ").map((word, index) => <motion.span key={`${word}-${index}`} initial={{ opacity: 0, y: 34, rotate: 2 }} animate={{ opacity: 1, y: 0, rotate: 0 }} transition={{ type: "spring", stiffness: 260, damping: 20, delay: index * .06 }}>{word}&nbsp;</motion.span>)}</motion.h1>
            <p className="intro-copy">Follow one function through its Git history: what changed, when it moved or disappeared, and what developers said along the way.</p>
            <motion.div className="intro-demo" aria-hidden="true"><svg viewBox="0 0 520 170"><motion.path d="M260 8V152" initial={{ pathLength: 0 }} animate={{ pathLength: [0, 1, 1] }} transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }} /><motion.circle cx="260" cy="42" r="10" initial={{ scale: 0 }} animate={{ scale: [0, 1, 1, 0] }} transition={{ duration: 4, repeat: Infinity, times: [0, .2, .8, 1] }} /><motion.rect x="248" y="88" width="24" height="24" initial={{ scale: 0 }} animate={{ scale: [0, 1, 1, 0] }} transition={{ duration: 4, repeat: Infinity, delay: .8, times: [0, .2, .8, 1] }} /><motion.path d="M250 145l10-18 10 18z" initial={{ scale: 0 }} animate={{ scale: [0, 1, 1, 0] }} transition={{ duration: 4, repeat: Infinity, delay: 1.7, times: [0, .2, .8, 1] }} /></svg><span>NEWER</span><span>OLDER</span></motion.div>
            <motion.button className="intro-button" disabled={symbolsLoading || !symbols.length} whileHover={{ y: -3 }} whileTap={{ scale: .98 }} onClick={() => { const first = symbols.find((symbol) => symbol.qualified_name.endsWith("format_filename")) ?? symbols[0]; if (first) setSelectedId(first.id); }}>Dig into format_filename <span>↗</span></motion.button>
          </motion.section>}
        </AnimatePresence>
        <footer className="main-footer"><span>EXCAVATOR <i>·</i> A FIELD NOTEBOOK FOR CODE</span><span>EXTRACTIVE RECORDS ONLY</span></footer>
      </motion.main>
      <aside className="evidence-panel" aria-label="Evidence and interpretation">
        <div className="evidence-head"><span className="panel-kicker">SOURCE MATERIAL</span><h2>Evidence</h2><p>Developer words stay verbatim. Model interpretation is marked separately.</p></div>
        {detailLoading ? <div className="evidence-wait">Loading evidence…</div> : detailError ? <p className="evidence-wait">Evidence could not be loaded.</p> : extractive ? <Unearthed data={extractive} selectedEvent={selectedEvent?.kind ?? null} /> : <div className="evidence-wait">Select a symbol to read its history and sources.</div>}
        <div className="evidence-divider" />
        {activeSymbol && <WhyChanged state={activeExplanation ?? { status: "loading" }} deleted={activeSymbol.status === "deleted"} onGenerate={() => void generateExplanation(activeSymbol.id)} onRetry={() => activeExplanation?.status === "error" && activeExplanation.retryAction === "load" ? loadExplanation(activeSymbol.id, true) : void generateExplanation(activeSymbol.id)} />}
      </aside>
    </div>
  </TooltipProvider></MotionConfig>;
}
