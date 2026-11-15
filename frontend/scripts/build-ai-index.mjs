import { access, readdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const demoDataRoot = fileURLToPath(new URL("../public/demo-data/", import.meta.url));
const symbolsRoot = join(demoDataRoot, "symbols");
const outputPath = join(demoDataRoot, "ai-symbols.json");
const entries = await readdir(symbolsRoot, { withFileTypes: true });
const symbolIds = [];

for (const entry of entries) {
  if (!entry.isDirectory() || !/^\d+$/.test(entry.name)) continue;
  try {
    await access(join(symbolsRoot, entry.name, "explanation.json"));
    symbolIds.push(Number(entry.name));
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
}

symbolIds.sort((left, right) => left - right);
await writeFile(outputPath, `${JSON.stringify(symbolIds, null, 2)}\n`, "utf8");
console.log(`Built derived AI index for ${symbolIds.length} symbol(s): ${outputPath}`);
