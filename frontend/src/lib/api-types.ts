export interface RepositoryRecord {
  id: number;
  owner: string;
  name: string;
  default_branch: string | null;
  indexing_status: string;
  head_sha_indexed: string | null;
  created_at: string;
  updated_at: string;
}

export interface SymbolRecord {
  id: number;
  repository_id: number;
  language: string;
  kind: "function" | "class" | "method";
  qualified_name: string;
  current_path: string | null;
  status: "exists" | "deleted";
}

export interface SymbolsResponse {
  items: SymbolRecord[];
  total: number;
}

export interface LineageVersion {
  commit_sha: string;
  commit_message: string;
  authored_at: string;
  path: string;
  qualified_name: string;
  start_line: number | null;
  end_line: number | null;
  body_hash: string | null;
  parse_status: "ok" | "syntax_error";
  lineage_method: "exact" | "rename_detected" | "heuristic";
}

export interface LineageResponse {
  symbol: SymbolRecord;
  versions: LineageVersion[];
}

export type ExtractiveSourceKind = "commit" | "pull_request" | "review_comment" | "issue";
export type LineageEvent = "added" | "modified" | "renamed" | "moved" | "removed";

export interface ExtractiveExtract {
  source_kind: ExtractiveSourceKind;
  reference: string | number;
  excerpt: string;
  lineage_event: LineageEvent | null;
  created_at: string;
  label: "quote";
  epistemic_label: "verified";
}

export interface ExtractiveExplanationResponse {
  status: "extracts" | "no_evidence";
  extracts: ExtractiveExtract[];
}

export type ExplanationStatus = "explained" | "insufficient_evidence";

export interface ExplanationQuote {
  snippet_id: string;
  source_type: "commit_message" | "pull_request" | "review_comment" | "issue";
  quote: string;
  level: string;
  epistemic_label: string;
}

export interface ExplanationClaim {
  position: number;
  text: string;
  quotes: ExplanationQuote[];
}

export interface StoredExplanationResponse {
  status: "explained";
  summary: string;
  claims: ExplanationClaim[];
}

export interface ExplainResponse {
  status: ExplanationStatus;
  summary: string | null;
  claims: ExplanationClaim[];
  dropped_claim_count: number;
  truncated: boolean;
  truncated_snippet_count: number;
  omitted_snippet_count: number;
}
