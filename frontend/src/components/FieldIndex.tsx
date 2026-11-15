import { AnimatePresence, motion } from "motion/react";
import { Search, Layers3, RotateCw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { RepositoryRecord, SymbolRecord } from "@/lib/api-types";
import { filterSymbols } from "@/lib/timeline";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { railVariants } from "@/motion";

interface Props {
  repositories: RepositoryRecord[]; repositoryId: number | null; onRepositoryChange: (id: number) => void;
  symbols: SymbolRecord[]; selectedId: number | null; onSelectSymbol: (id: number) => void;
  query: string; onQueryChange: (query: string) => void; loading: boolean; error: string | null; onRetry: () => void;
  motionOn: boolean; onMotionChange: (enabled: boolean) => void;
  demoMode: boolean; demoAiSymbolIds: ReadonlySet<number>;
}

export function FieldIndex(props: Props) {
  const [kindFilter, setKindFilter] = useState<SymbolRecord["kind"] | "all">("all");
  const [aiOnly, setAiOnly] = useState(false);
  const filtered = useMemo(() => filterSymbols(props.symbols, props.query)
    .filter((symbol) => kindFilter === "all" || symbol.kind === kindFilter)
    .filter((symbol) => !aiOnly || props.demoAiSymbolIds.has(symbol.id)), [props.symbols, props.query, kindFilter, aiOnly, props.demoAiSymbolIds]);
  const selectedRepo = props.repositories.find((repo) => repo.id === props.repositoryId);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "/" && !(event.target instanceof HTMLInputElement)) { event.preventDefault(); searchRef.current?.focus(); }
      if (event.key === "Escape") setDrawerOpen(false);
      if ((event.key === "ArrowDown" || event.key === "ArrowUp") && filtered.length) {
        const current = filtered.findIndex((item) => item.id === props.selectedId);
        const next = Math.max(0, Math.min(filtered.length - 1, current + (event.key === "ArrowDown" ? 1 : -1)));
        if (filtered[next]) { event.preventDefault(); props.onSelectSymbol(filtered[next].id); }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [filtered, props.selectedId, props.onSelectSymbol]);
  return <>
    <button className="drawer-toggle" onClick={() => setDrawerOpen(true)}>Browse symbols</button>
    <motion.aside className={`field-rail ${drawerOpen ? "drawer-open" : ""}`} variants={railVariants} initial="hidden" animate="visible">
      <div className="wordmark"><span className="wordmark-mark">E</span><span>EXCAVATOR<small>CODE HISTORY, UNEARTHED</small></span></div>
      <div className="rail-section">
        <label className="eyebrow" htmlFor="repository-select">Repository</label>
        <Select value={props.repositoryId === null ? "" : String(props.repositoryId)} onValueChange={(value) => props.onRepositoryChange(Number(value))}>
          <SelectTrigger id="repository-select" className="repo-select"><SelectValue placeholder="Choose a repository" /></SelectTrigger>
          <SelectContent>{props.repositories.map((repo) => <SelectItem key={repo.id} value={String(repo.id)}>{repo.owner}/{repo.name}</SelectItem>)}</SelectContent>
        </Select>
        {props.demoMode && <span className="sample-data-badge" role="status">SAMPLE DATA</span>}
        {selectedRepo && <p className="repo-branch">{selectedRepo.default_branch ?? "branch unknown"} · {selectedRepo.indexing_status}</p>}
      </div>
      <Separator className="rail-rule" />
      <div className="symbol-heading"><span className="eyebrow">Symbols</span><Badge variant="outline">{props.symbols.length}</Badge></div>
      <div className="search-wrap"><Search size={14} aria-hidden="true" /><Input ref={searchRef} aria-label="Search symbols" placeholder="Name, path, kind…" value={props.query} onChange={(event) => props.onQueryChange(event.target.value)} /></div>
      <div className="kind-filters" aria-label="Filter symbols by kind">{(["all", "function", "class", "method"] as const).map((kind) => <button type="button" key={kind} className={kindFilter === kind ? "active" : ""} aria-pressed={kindFilter === kind} onClick={() => setKindFilter(kind)}>{kind === "all" ? "All" : `${kind[0]?.toUpperCase()}${kind.slice(1)}`}</button>)}</div>
      {props.demoMode && <label className="ai-filter-toggle"><input type="checkbox" checked={aiOnly} onChange={(event) => setAiOnly(event.target.checked)} /><span>Only with AI explanation</span></label>}
      <ScrollArea className="specimen-scroll">
        {props.loading ? <div className="loading-list" aria-label="Loading symbols">{[0, 1, 2, 3, 4].map((n) => <Skeleton key={n} className="h-[62px] w-full" />)}</div> : props.error ? <div className="rail-message"><p>{props.error}</p><Button variant="outline" size="sm" onClick={props.onRetry}><RotateCw /> Retry</Button></div> : filtered.length ? <div className="specimen-list">
          <AnimatePresence initial={false}>{filtered.map((symbol, index) => <motion.button layout key={symbol.id} className={`specimen-row ${props.selectedId === symbol.id ? "is-selected" : ""}`} onClick={() => props.onSelectSymbol(symbol.id)} initial={{ opacity: 0, y: 7 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -5 }} transition={{ duration: 0.2, delay: Math.min(index * 0.018, 0.12) }}>
            {props.selectedId === symbol.id && <motion.span className="selection-mark" layoutId="selected-specimen" />}
            <span className="specimen-main"><motion.span layoutId={`symbol-title-${symbol.id}`} className="specimen-name">{symbol.qualified_name}{props.demoMode && props.demoAiSymbolIds.has(symbol.id) && <span className="ai-marker" title="Saved AI explanation" aria-label="Saved AI explanation">AI</span>}</motion.span><span className="specimen-path">{symbol.current_path ?? "location unknown"}</span></span>
            <span className="specimen-meta"><Badge variant="outline" className={`kind-badge kind-${symbol.kind}`}>{symbol.kind}</Badge><span className={`symbol-status ${symbol.status}`}><i />{symbol.status === "deleted" ? "Removed" : "Alive"}</span></span>
          </motion.button>)}</AnimatePresence>
        </div> : <div className="rail-empty"><Layers3 size={18} /><p>{props.symbols.length ? "No symbols match this search." : "No symbols indexed yet."}</p></div>}
      </ScrollArea>
      <div className="rail-footer"><span className="status-lamp" /> INDEX READY <label className="motion-switch"><input type="checkbox" checked={props.motionOn} onChange={(event) => props.onMotionChange(event.target.checked)} /><span>Motion</span></label></div>
      <button className="drawer-close" aria-label="Close explorer" onClick={() => setDrawerOpen(false)}>×</button>
    </motion.aside>
  </>;
}
