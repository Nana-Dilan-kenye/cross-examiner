import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadHMEM } from "./src/engine.ts";

const here = path.dirname(fileURLToPath(import.meta.url));

async function main() {
  const [command, ...args] = process.argv.slice(2);
  const { HMEM } = await loadHMEM();
  // The store lives with the engine by default. A container or a second
  // checkout can point it somewhere else.
  const persistDir = process.env.HMEM_PERSIST_DIR || path.join(here, ".notebook");
  const hmem = new HMEM({ persistDir, actor: "cross-examiner" });

  if (command === "remember") {
    const input = JSON.parse(args.join(" "));
    const record = hmem.add({
      content: input.content,
      type: "factual",
      layer: "working",
      tags: ["cross-examiner", ...(input.tags ?? [])],
      source: input.source,
      confidence: input.confidence ?? 0.7,
      provenance: {
        origin: "file_save",
        learnedAt: Date.now(),
        label: "Cross-Examiner finding",
        refs: input.refs ?? [],
      },
    });
    console.log(JSON.stringify({ ok: true, id: record.id, content: record.content }));
  } else if (command === "query") {
    // The retrieval is a relevance ranking over every memory, so the
    // candidate list has to be wide enough for a topic-specific memory to
    // survive it. The caller filters by topic afterwards.
    const topN = Number(process.env.HMEM_TOP_N || "25");
    const result = hmem.query(args.join(" "), { threshold: 0.1, topN });
    console.log(JSON.stringify({
      context: result.context,
      memories: result.memories.map(({ memory, relevance }) => ({
        id: memory.id,
        content: memory.content,
        source: memory.source,
        refs: memory.provenance.refs ?? [],
        confidence: memory.confidence,
        relevance,
      })),
      trace: result.trace,
    }));
  } else {
    console.error('Usage: npx tsx cross_examiner_memory.ts remember \'{"content":"...","source":"..."}\' | query "question"');
    process.exitCode = 2;
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
