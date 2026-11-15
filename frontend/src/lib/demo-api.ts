import { ApiError } from "@/lib/api-error";

let aiSymbolIdsPromise: Promise<Set<number>> | null = null;

function fixturePath(path: string): string {
  const endpoint = path.split("?", 1)[0];
  if (endpoint === "/repositories") return "/repositories.json";

  const symbolsMatch = endpoint.match(/^\/repositories\/(\d+)\/symbols$/);
  if (symbolsMatch) return `/repositories/${symbolsMatch[1]}/symbols.json`;

  const symbolMatch = endpoint.match(/^\/symbols\/(\d+)\/(lineage|extractive-explanation|explanation)$/);
  if (symbolMatch) {
    const [, symbolId, resource] = symbolMatch;
    const filename = resource === "extractive-explanation" ? "extractive-explanation" : resource;
    return `/symbols/${symbolId}/${filename}.json`;
  }

  throw new ApiError("This request is not available in the sample demo.", 404);
}

export function getDemoAiSymbolIds(): Promise<Set<number>> {
  if (aiSymbolIdsPromise) return aiSymbolIdsPromise;
  const baseUrl = `${import.meta.env.BASE_URL}demo-data`.replace(/\/$/, "");
  aiSymbolIdsPromise = fetch(`${baseUrl}/ai-symbols.json`, {
    headers: { Accept: "application/json" },
  }).then(async (response) => {
    if (!response.ok) throw new ApiError(`The saved AI index returned ${response.status}.`, response.status);
    const data: unknown = await response.json();
    if (!Array.isArray(data) || data.some((id) => !Number.isInteger(id) || id < 1)) {
      throw new ApiError("The saved AI index is not valid.");
    }
    return new Set(data as number[]);
  }).catch((error) => {
    aiSymbolIdsPromise = null;
    if (error instanceof ApiError) throw error;
    throw new ApiError("The saved AI index could not be reached.");
  });
  return aiSymbolIdsPromise;
}

export async function requestDemoJson<T>(
  path: string,
  method: "GET" | "POST" = "GET",
): Promise<T> {
  if (method !== "GET") {
    throw new ApiError("Sample mode uses saved data and cannot generate new results.", 405);
  }

  const baseUrl = `${import.meta.env.BASE_URL}demo-data`.replace(/\/$/, "");
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${fixturePath(path)}`, {
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new ApiError("The saved sample data could not be reached.");
  }

  if (!response.ok) {
    if (response.status === 404 && path.endsWith("/explanation")) {
      throw new ApiError("explanation not found", 404);
    }
    throw new ApiError(`The saved sample data returned ${response.status}.`, response.status);
  }

  if (path.endsWith("/explanation") && !response.headers.get("content-type")?.includes("application/json")) {
    throw new ApiError("explanation not found", 404);
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError("The saved sample data is not valid JSON.", response.status);
  }
}
