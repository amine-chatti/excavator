import { AnimatePresence, motion } from "motion/react";
import { Search, Layers3, RotateCw } from "lucide-react";
import { useMemo } from "react";
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
  repositories: RepositoryRecord[];
  repositoryId: number | null;
  onRepositoryChange: (id: number) => void;
  symbols: SymbolRecord[];
  selectedId: number | null;
  onSelectSymbol: (id: number) => void;
  query: string;
  onQueryChange: (query: string) => void;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}

export function FieldIndex(props: Props) {
  const filtered = useMemo(() => filterSymbols(props.symbols, props.query), [props.symbols, props.query]);
  const selectedRepo = props.repositories.find((repo) => repo.id === props.repositoryId);
  return (
    <motion.aside className="field-rail" variants={railVariants} initial="hidden" animate="visible">
      <div className="wordmark"><span className="wordmark-mark">E</span><span>EXCAVATOR<small>FIELD NOTEBOOK · 01</small></span></div>
      <div className="rail-section">
        <label className="eyebrow" htmlFor="repository-select">Repository</label>
        <Select value={props.repositoryId === null ? undefined : String(props.repositoryId)} onValueChange={(value) => props.onRepositoryChange(Number(value))}>
          <SelectTrigger id="repository-select" className="repo-select"><SelectValue placeholder="Choose a dig site" /></SelectTrigger>
          <SelectContent>{props.repositories.map((repo) => <SelectItem key={repo.id} value={String(repo.id)}>{repo.owner}/{repo.name}</SelectItem>)}</SelectContent>
        </Select>
        {selectedRepo && <p className="repo-branch">↳ {selectedRepo.default_branch ?? "branch unknown"} <span>· {selectedRepo.indexing_status}</span></p>}
      </div>
      <Separator className="rail-rule" />
      <div className="symbol-heading"><span className="eyebrow">Specimens</span><Badge variant="outline">{props.symbols.length}</Badge></div>
      <div className="search-wrap"><Search size={14} aria-hidden="true" /><Input aria-label="Search symbols" placeholder="Name, path, kind…" value={props.query} onChange={(event) => props.onQueryChange(event.target.value)} /></div>
      <ScrollArea className="specimen-scroll">
        {props.loading ? <div className="loading-list" aria-label="Loading symbols">{[0, 1, 2, 3, 4].map((n) => <Skeleton key={n} className="h-[62px] w-full" />)}</div> : props.error ? <div className="rail-message"><p>{props.error}</p><Button variant="outline" size="sm" onClick={props.onRetry}><RotateCw /> Retry</Button></div> : filtered.length ? <div className="specimen-list">
          <AnimatePresence initial={false}>{filtered.map((symbol, index) => <motion.button layout key={symbol.id} className={`specimen-row ${props.selectedId === symbol.id ? "is-selected" : ""}`} onClick={() => props.onSelectSymbol(symbol.id)} initial={{ opacity: 0, y: 7 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -5 }} transition={{ duration: 0.2, delay: Math.min(index * 0.018, 0.12) }}>
            {props.selectedId === symbol.id && <motion.span className="selection-mark" layoutId="selected-specimen" />}
            <span className="specimen-main"><span className="specimen-name">{symbol.qualified_name}</span><span className="specimen-path">{symbol.current_path ?? "location unknown"}</span></span>
            <span className="specimen-meta"><Badge variant="outline">{symbol.kind}</Badge><span className={`status-dot ${symbol.status}`} title={symbol.status} /></span>
          </motion.button>)}</AnimatePresence>
        </div> : <div className="rail-empty"><Layers3 size={18} /><p>{props.symbols.length ? "No specimens match this search." : "No symbols indexed yet."}</p></div>}
      </ScrollArea>
      <div className="rail-footer"><span className="status-lamp" /> LOCAL ARCHIVE <span>·</span> NO GENERATION</div>
    </motion.aside>
  );
}
