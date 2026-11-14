import type {
  ExtractiveExplanationResponse,
  LineageResponse,
  RepositoryRecord,
  SymbolsResponse,
} from "@/lib/api-types";

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function requestJson<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new ApiError("The field server could not be reached.");
  }
  if (!response.ok) {
    throw new ApiError(`The field server returned ${response.status}.`, response.status);
  }
  return (await response.json()) as T;
}

export function listRepositories(): Promise<RepositoryRecord[]> {
  return requestJson<RepositoryRecord[]>("/repositories");
}

export function listSymbols(repositoryId: number): Promise<SymbolsResponse> {
  return requestJson<SymbolsResponse>(`/repositories/${repositoryId}/symbols`);
}

export function getLineage(symbolId: number): Promise<LineageResponse> {
  return requestJson<LineageResponse>(`/symbols/${symbolId}/lineage`);
}

export function getExtractiveExplanation(
  symbolId: number,
): Promise<ExtractiveExplanationResponse> {
  return requestJson<ExtractiveExplanationResponse>(
    `/symbols/${symbolId}/extractive-explanation`,
  );
}
