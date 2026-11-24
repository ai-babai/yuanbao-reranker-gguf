---
type: Integration Guide
description: Replace QMD's default reranker with Yuanbao-Reranker-0.6B Q8_0 GGUF via models.rerank and reproduce the Russian hybrid search check.
created: "2026-11-24"
---
# Yuanbao-Reranker-0.6B GGUF as the QMD reranker

Use this guide to replace QMD's default Qwen3-Reranker-0.6B with Yuanbao for
Russian Markdown search. QMD 2.9.0 loads `Yuanbao-Reranker-0.6B-Q8_0.gguf` directly through `models.rerank`. Its SDK and CLI both ran the packaged node-llama-cpp 3.22.3 Metal backend on Apple M4 Pro. The examples use QMD's default EmbeddingGemma and typed queries, which supply their own lexical and vector terms and skip query expansion. [QMD 2.9.0](https://github.com/tobi/qmd/releases/tag/v2.9.0) · [node-llama-cpp 3.22.3](https://github.com/withcatai/node-llama-cpp/releases/tag/v3.22.3)

## Isolated install

Set `GGUF_ROOT` to the absolute path of an artifact directory outside the Git checkout. Place the GGUF at `$GGUF_ROOT/weights/Yuanbao-Reranker-0.6B-Q8_0.gguf`. Use Node.js 22 or newer, as required by QMD. The check used Node.js 25.9.0 and npm 11.12.1.

```sh
: "${GGUF_ROOT:?Set GGUF_ROOT to the absolute artifact directory}"
qmd_dir="$GGUF_ROOT/tools/qmd"
mkdir -p "$qmd_dir/home" "$qmd_dir/config" "$qmd_dir/cache" \
  "$qmd_dir/data" "$qmd_dir/state" "$qmd_dir/tmp" "$GGUF_ROOT/temp"

run_isolated() {
  env -i PATH="$qmd_dir/node_modules/.bin:$PATH" LANG=en_US.UTF-8 \
    HOME="$qmd_dir/home" XDG_CONFIG_HOME="$qmd_dir/config" \
    XDG_CACHE_HOME="$qmd_dir/cache" XDG_DATA_HOME="$qmd_dir/data" \
    XDG_STATE_HOME="$qmd_dir/state" TMPDIR="$qmd_dir/tmp" \
    npm_config_cache="$qmd_dir/cache/npm" \
    npm_config_userconfig="$qmd_dir/home/.npmrc" \
    npm_config_globalconfig="$qmd_dir/home/global.npmrc" "$@"
}

cat > "$qmd_dir/package.json" <<'JSON'
{
  "name": "yuanbao-qmd-integration",
  "private": true,
  "dependencies": {
    "@tobilu/qmd": "2.9.0",
    "node-llama-cpp": "3.22.3"
  }
}
JSON
if [ ! -f "$qmd_dir/package-lock.json" ]; then
  run_isolated npm --prefix "$qmd_dir" install --package-lock-only --no-audit --no-fund
fi
run_isolated npm --prefix "$qmd_dir" ci --no-audit --no-fund
run_isolated qmd --version
```

Keep `tools/qmd/package-lock.json` for repeat installs. The lock generated for this run has SHA-256 `84203225223628a3b526a793b944683d4070fbc268a1ab1fb15fd5f4fba6c629`.

## Local index and search

```sh
workspace="$(mktemp -d "$GGUF_ROOT/temp/qmd-smoke.XXXXXXXX")"
mkdir -p "$workspace/docs" "$workspace/.qmd"
cat > "$workspace/.qmd/index.yml" <<YAML
collections:
  rubq:
    path: ./docs
    pattern: "**/*.md"
models:
  rerank: "$GGUF_ROOT/weights/Yuanbao-Reranker-0.6B-Q8_0.gguf"
YAML
```

Put Russian Markdown documents in `$workspace/docs`. For the results below, use these three passages from the [pinned RuBQ corpus](https://huggingface.co/datasets/mteb/RuBQReranking/tree/f2eac2f1f82445938af650c2a285a34dd77a16eb). In each file, write the Markdown heading shown, then a paragraph containing `Справка`, then the stripped `text` field of the corresponding corpus row.

| File | Heading | Corpus ID |
| --- | --- | --- |
| `limpopo.md` | Лимпопо | `apositive_test_query9_00000` |
| `uncle-tom.md` | Хижина дяди Тома | `apositive_test_query1_00000` |
| `winter-palace.md` | Зимний дворец | `apositive_test_query6_00000` |

```sh
cd "$workspace"
run_isolated qmd trust
run_isolated qmd update
run_isolated qmd embed
```

`qmd trust` approves the custom model in this project-local config. Review the config before approving it again after a model path change. QMD keeps the database at `.qmd/index.sqlite`. The first embed downloads `embeddinggemma-300M-Q8_0.gguf` to the isolated cache. The typed searches below use that model and the local Yuanbao model. [Project-local config and typed queries](https://github.com/tobi/qmd/blob/v2.9.0/README.md)

```sh
question='Кто написал роман «Хижина дяди Тома»?'
query="$(printf 'lex: %s\nvec: %s\nintent: %s\n' 'хижина' "$question" "$question")"
run_isolated qmd query "$query" -c rubq -n 3 --format json --explain

question='Кто создал Зимний дворец в Санкт-Петербурге?'
query="$(printf 'lex: %s\nvec: %s\nintent: %s\n' '"зимний дворец"' "$question" "$question")"
run_isolated qmd query "$query" -c rubq -n 3 --format json --explain
```

QMD uses the first `lex` query as the primary rerank text and prepends `intent`. Use the Russian question as `intent` here so the reranker sees the full question as well as the search term. The JSON field `explain.rerankScore` reports the model score. `explain.blendedScore` combines it with the retrieval rank.

## SDK check with fixed retrieval

Run this from the same shell after creating the config and documents. The SDK builds a separate lexical index. It supplies a constant lexical term and changes the Russian question via `intent`, so both searches start from the same candidates in the same retrieval order.

```sh
(
  cd "$qmd_dir"
  run_isolated env QMD_WORKSPACE="$workspace" GGML_METAL_NO_RESIDENCY=1 \
    node --input-type=module <<'JS'
import { join } from "node:path";
import { createStore } from "@tobilu/qmd";

const workspace = process.env.QMD_WORKSPACE;
const store = await createStore({
  dbPath: join(workspace, "sdk.sqlite"),
  configPath: join(workspace, ".qmd/index.yml"),
});
try {
  await store.update();
  for (const intent of [
    "Кто написал роман «Хижина дяди Тома»?",
    "Кто создал Зимний дворец в Санкт-Петербурге?",
  ]) {
    const results = await store.search({
      queries: [{ type: "lex", query: "Справка" }],
      collections: ["rubq"],
      intent,
      rerank: true,
      explain: true,
      limit: 3,
    });
    console.log(intent, results.map(({ file, explain }) => ({
      file,
      rrfRank: explain.rrf.rank,
      rerankScore: explain.rerankScore,
    })));
  }
} finally {
  await store.close();
}
JS
)
```

## Observed results

| Hybrid query | Result order | First result's rerank score |
| --- | --- | ---: |
| Кто написал роман «Хижина дяди Тома»? | `uncle-tom.md`, `winter-palace.md`, `limpopo.md` | 0.9993739128 |
| Кто создал Зимний дворец в Санкт-Петербурге? | `winter-palace.md`, `uncle-tom.md`, `limpopo.md` | 0.9981061220 |

In the fixed-retrieval SDK check, `limpopo.md` held retrieval rank 1 for both questions. The raw reranker put `uncle-tom.md` first for the novel question (0.9994880) and `winter-palace.md` first for the palace question (0.9981351). QMD's blended list kept `limpopo.md` first and swapped the other two. QMD 2.9.0 assigns 75% weight to retrieval position for the top three candidates. [Released blending implementation](https://github.com/tobi/qmd/blob/v2.9.0/src/store.ts)

- The SDK and CLI loaded the configured Yuanbao file, created 4,096-token ranking contexts with rank pooling (type 4), and called `rankAll`. The packaged runtime reported llama.cpp `v0.9.0` and 29 Metal-offloaded Yuanbao layers. The loaded 639,155,136-byte GGUF has SHA-256 `4c051aa4d4ea7276fdbef78b1a97869929b241f9812ffffdeeff35b431473912`.
- A fresh CLI index started with zero model-cache rows. Each of four distinct hybrid searches wrote three results to SQLite's `llm_cache` and had a `rankAll` trace. The `--no-rerank` control produced zero rerank scores without adding cache rows. A warm same-model control returned cached scores without a `rankAll` call. A copy of that populated index pointed to a missing GGUF and exited with status 1 on the same question, leaving the 12 existing cache rows intact. QMD keys rerank results by the configured model identity. Use a fresh index or a new model path when replacing the bytes of a model at the same path. [QMD cache fix](https://github.com/tobi/qmd/pull/848)
- On macOS 15.8.1 with M4 Pro, `/usr/bin/time -lp` measured 13.07 s and 1.78 s for the two subject-keyword queries, with peak RSS of 3,695,411,200 and 3,699,687,424 bytes. Two additional hybrid queries with the common keyword `Справка` took 1.93 s and 1.56 s, with peak RSS of 3,710,730,240 and 3,690,184,704 bytes. Each launched a fresh process, loaded both cached weight files, embedded one query, and reranked three chunks with empty score entries for the query. These individual timings include startup and first use of both models. The OS filesystem cache was uncontrolled.

## "Failed to create any rerank context"

QMD reports this error when it cannot create a ranking context for the
configured reranker. [QMD issue #721](https://github.com/tobi/qmd/issues/721)
shows it with another Qwen3 reranker GGUF. In the check above, QMD 2.9.0 created
rank-pooling contexts for this Q8_0 file. If you see the error with it, compare
the SHA-256 of the file with `SHA256SUMS` and the QMD and node-llama-cpp
versions with the ones listed here.

## Evidence

Local evidence under `$GGUF_ROOT/integrations/qmd/` includes `index.yml`, `versions.txt`, `sdk.jsonl`, both `natural-*.json` results and their trace/timing logs, the `*-commands.log` command records, cache counts, `cli-missing.log`, and `verification.log`. The temporary trace delegated to the released node-llama-cpp methods with their original arguments. The check used three passages and the disposable index and documents were removed afterward.
