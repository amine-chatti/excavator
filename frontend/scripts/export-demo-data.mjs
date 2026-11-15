import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const apiBase = (process.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const outputRoot = fileURLToPath(new URL("../public/demo-data/", import.meta.url));
const pageSize = 50;
let fileCount = 0;
let bytesWritten = 0;
let redactionCount = 0;
let symbolCount = 0;
let savedExplanationCount = 0;

const secretPatterns = [
  [/-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----/g, "[REDACTED PRIVATE KEY]"],
  [/\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b/g, "[REDACTED GITHUB TOKEN]"],
  [/\bsk-ant-[A-Za-z0-9_-]{20,}\b/g, "[REDACTED API KEY]"],
  [/\bAKIA[0-9A-Z]{16}\b/g, "[REDACTED ACCESS KEY]"],
  [/\bBearer\s+[A-Za-z0-9._~+/-]{20,}/gi, "Bearer [REDACTED]"],
  [/((?:api[_ -]?key|access[_ -]?token|github[_ -]?token|anthropic[_ -]?api[_ -]?key|password|passwd|secret|authorization)\s*[:=]\s*["']?)[^"'\s,;]+/gi, "$1[REDACTED]"],
  [/(\b(?:postgres(?:ql)?|mysql):\/\/[^:/\s]+:)[^@\s]+(@)/gi, "$1[REDACTED]$2"],
];

function redact(value) {
  if (typeof value === "string") {
    return secretPatterns.reduce((text, [pattern, replacement]) => text.replace(pattern, () => {
      redactionCount += 1;
      return replacement;
    }), value);
  }
  if (Array.isArray(value)) return value.map(redact);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, redact(item)]));
  }
  return value;
}

async function getJson(endpoint, { missingExplanationAllowed = false } = {}) {
  let response;
  try {
    response = await fetch(`${apiBase}${endpoint}`, { headers: { Accept: "application/json" } });
  } catch {
    throw new Error(`Could not reach the local Excavator API for ${endpoint}.`);
  }

  if (missingExplanationAllowed && response.status === 404) {
    let detail;
    try {
      detail = (await response.json()).detail;
    } catch {
      detail = undefined;
    }
    if (detail === "explanation not found") return null;
  }

  if (!response.ok) throw new Error(`The API request ${endpoint} returned ${response.status}.`);
  try {
    return await response.json();
  } catch {
    throw new Error(`The API response for ${endpoint} was not valid JSON.`);
  }
}

async function saveJson(relativePath, responseData) {
  const destination = join(outputRoot, relativePath);
  const content = `${JSON.stringify(redact(responseData), null, 2)}\n`;
  await mkdir(dirname(destination), { recursive: true });
  await writeFile(destination, content, "utf8");
  fileCount += 1;
  bytesWritten += Buffer.byteLength(content, "utf8");
}

const repositories = await getJson("/repositories");
if (!Array.isArray(repositories)) throw new Error("GET /repositories did not return a list.");
await saveJson("repositories.json", repositories);

for (const repository of repositories) {
  const allSymbols = [];
  for (let offset = 0; ; offset += pageSize) {
    const page = await getJson(`/repositories/${repository.id}/symbols?limit=${pageSize}&offset=${offset}`);
    if (!Array.isArray(page?.items) || typeof page.total !== "number") {
      throw new Error(`The symbols response for repository ${repository.id} had an unexpected shape.`);
    }
    const filename = offset === 0 ? "symbols.json" : `symbols-offset-${offset}.json`;
    await saveJson(join("repositories", String(repository.id), filename), page);
    allSymbols.push(...page.items);
    if (offset + page.items.length >= page.total) break;
    if (page.items.length === 0) throw new Error(`The symbols response for repository ${repository.id} stopped before all items were read.`);
  }

  for (const symbol of allSymbols) {
    symbolCount += 1;
    await saveJson(join("symbols", String(symbol.id), "lineage.json"), await getJson(`/symbols/${symbol.id}/lineage`));
    await saveJson(join("symbols", String(symbol.id), "extractive-explanation.json"), await getJson(`/symbols/${symbol.id}/extractive-explanation`));
    const explanation = await getJson(`/symbols/${symbol.id}/explanation`, { missingExplanationAllowed: true });
    if (explanation !== null) {
      await saveJson(join("symbols", String(symbol.id), "explanation.json"), explanation);
      savedExplanationCount += 1;
    }
  }
}

const megabytes = (bytesWritten / (1024 * 1024)).toFixed(2);
console.log(`Export complete: ${repositories.length} repositories, ${symbolCount} symbols, ${savedExplanationCount} saved AI explanations.`);
console.log(`Wrote ${fileCount} JSON files (${bytesWritten} bytes; ${megabytes} MiB).`);
if (redactionCount) console.log(`Redacted ${redactionCount} secret-like value(s); JSON field names and structure were preserved.`);
console.log("Saved files in frontend/public/demo-data.");
