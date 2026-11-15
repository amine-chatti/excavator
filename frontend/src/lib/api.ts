import type {
  ExtractiveExplanationResponse,
  ExplainResponse,
  LineageResponse,
  RepositoryRecord,
  StoredExplanationResponse,
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

async function requestJson<T>(path: string, method: "GET" | "POST" = "GET"): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new ApiError("The field server could not be reached.");
  }
  if (!response.ok) {
    let detail: unknown;
    try {
      detail = (await response.json()) as { detail?: unknown };
      detail = typeof detail === "object" && detail !== null && "detail" in detail
        ? detail.detail
        : undefined;
    } catch {
      detail = undefined;
    }
    const serverMessage = typeof detail === "string" ? detail : `The field server returned ${response.status}.`;
    throw new ApiError(serverMessage, response.status);
  }
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError("The field server returned an unreadable response.", response.status);
  }
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

export async function getStoredExplanation(symbolId: number): Promise<StoredExplanationResponse | null> {
  try {
    return await requestJson<StoredExplanationResponse>(`/symbols/${symbolId}/explanation`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404 && error.message === "explanation not found") {
      return null;
    }
    throw error;
  }
}

export function postExplanation(symbolId: number): Promise<ExplainResponse> {
  return requestJson<ExplainResponse>(`/symbols/${symbolId}/explain`, "POST");
}
