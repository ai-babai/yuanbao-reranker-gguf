---
type: Benchmark Report
description: RuBQ pilot ranking, exact-tie sensitivity, and Apple Metal performance for the four GGUFs.
created: "2026-11-24"
---

# RuBQ pilot on llama.cpp Metal

The same 150 Russian queries, 3,656 candidate pairs and 259 positive labels were scored by each GGUF.
This pilot measures reranking on preselected candidates from RuBQ.

| Model | nDCG@10 | MRR@10 | Relevant top 1 | Top 1 changes vs F16 | GGUF MiB |
|---|---:|---:|---:|---:|---:|
| Yuanbao F16 | 0.8476 | 0.8408 | 113 | — | 1142.2 |
| Yuanbao Q8_0 | 0.8480 | 0.8408 | 113 | 0 | 609.5 |
| Yuanbao Q4_K_M | 0.8488 | 0.8391 | 112 | 10 | 378.1 |
| Qwen Q8_0 (ggml-org) | 0.8124 | 0.7949 | 102 | 30 | 609.5 |
| Yuanbao BF16 (earlier MPS pilot) | 0.8488 | 0.8419 | 113 | 2 | — |

Yuanbao Q8_0 improved mean nDCG@10 by +0.0355 (95% CI +0.0184 to +0.0536) and mean MRR@10 by +0.0459 (95% CI +0.0185 to +0.0735) relative to shipped Qwen Q8_0.
The paired percentile bootstrap used 10,000 draws of the 150 queries with replacement, seed `0` (NumPy PCG64), and the same draws for both metrics.

## Exact ties

Stable evaluation breaks score ties by original candidate order, which favors positives on RuBQ.
Within exactly tied scores, put lower labels first for the low bound and higher labels first for the high bound.

| Model | Queries with ties | Tied top 1 | Mixed-label tie | nDCG@10 range | MRR@10 range |
|---|---:|---:|---:|---:|---:|
| Yuanbao F16 | 6 | 0 | 2 | 0.8474–0.8476 | 0.8408–0.8408 |
| Yuanbao Q8_0 | 6 | 0 | 2 | 0.8478–0.8480 | 0.8408–0.8408 |
| Yuanbao Q4_K_M | 6 | 0 | 2 | 0.8486–0.8488 | 0.8391–0.8391 |
| Qwen Q8_0 (ggml-org) | 6 | 0 | 2 | 0.8123–0.8124 | 0.7949–0.7949 |
| Yuanbao BF16 (earlier MPS pilot) | 142 | 5 | 16 | 0.8414–0.8488 | 0.8327–0.8419 |

## Raw score agreement

Each row compares all 3,656 aligned probability scores and counts queries whose top document changed.

| Baseline | Compared with | Score MAE | Absolute error p95 | Pearson r | Top 1 changed | Gained / lost relevant top 1 |
|---|---|---:|---:|---:|---:|---:|
| Yuanbao F16 | Yuanbao Q8_0 | 0.00133 | 0.00761 | 0.9999 | 0 | 0 / 0 |
| Yuanbao F16 | Yuanbao Q4_K_M | 0.01528 | 0.08538 | 0.9928 | 10 | 2 / 3 |
| Yuanbao F16 | Qwen Q8_0 (ggml-org) | 0.07032 | 0.47775 | 0.9156 | 30 | 2 / 13 |
| Yuanbao Q8_0 | Yuanbao Q4_K_M | 0.01524 | 0.08624 | 0.9929 | 10 | 2 / 3 |
| Yuanbao Q8_0 | Qwen Q8_0 (ggml-org) | 0.07002 | 0.47343 | 0.9161 | 30 | 2 / 13 |
| Yuanbao Q4_K_M | Qwen Q8_0 (ggml-org) | 0.07015 | 0.46247 | 0.9193 | 29 | 2 / 12 |
| Yuanbao F16 | Yuanbao BF16 (earlier MPS pilot) | 0.00220 | 0.01294 | 0.9999 | 2 | 0 / 0 |

## Input boundary

Unmodified `POST /v1/rerank` used each GGUF’s embedded template. The four templates matched the
Horizon wrapper byte for byte, including the single field newlines and the full assistant suffix.
Each GGUF’s `/tokenize` generated separate prefix, body and suffix IDs. The body was clipped inside
the 512-token total. The client supplied the longest valid document prefix up to that byte cut,
tokenized the rendered prompt again, checked the suffix and ceiling, and reconciled the request’s
aggregate token count against the server response.

| Model | Body clipped | Exact target IDs | Fallback deltas (tokens → pairs) | UTF‑8 tail bytes dropped | At 512 |
|---|---:|---:|---|---:|---:|
| Yuanbao F16 | 168 | 3656 | — | 0 | 170 |
| Yuanbao Q8_0 | 168 | 3656 | — | 0 | 170 |
| Yuanbao Q4_K_M | 168 | 3656 | — | 0 | 170 |
| Qwen Q8_0 (ggml-org) | 168 | 3656 | — | 0 | 170 |

The earlier BF16/MPS run used the same logical token budget via direct token submission.
It is a cross-runtime reference. The stock API consumes UTF‑8 text.

## Latency and memory

Apple M4 Pro, 48 GiB unified memory, macOS 15.8.1.
llama.cpp [5fddd0b](https://github.com/ggml-org/llama.cpp/tree/5fddd0b99888a90260736e0f734fa8e160064e03) (version: 1.0.0-dev (build 1, commit 5fddd0b)). All layers offloaded to Metal with Flash Attention.
One server and one in-flight request at a time. Prompt caching disabled. Every timed configuration
used eight slots (768 runtime context tokens per slot) and a 512-token input ceiling.

| Model | Cold ready ms | First 25 ms | 10 docs median / p95 ms | 25 docs median / p95 ms | 50 docs median / p95 ms | Peak RSS GiB | Peak footprint GiB |
|---|---:|---:|---:|---:|---:|---:|---:|
| Yuanbao F16 | 283 | 1055 | 549 / 631 | 1218 / 1370 | 2493 / 2579 | 1.94 | 0.95 |
| Yuanbao Q8_0 | 248 | 1079 | 513 / 519 | 1262 / 1305 | 2486 / 2595 | 1.42 | 0.86 |
| Yuanbao Q4_K_M | 229 | 1096 | 482 / 512 | 1277 / 1321 | 2578 / 2934 | 1.19 | 0.88 |
| Qwen Q8_0 (ggml-org) | 250 | 1165 | 577 / 596 | 1377 / 1501 | 2905 / 3121 | 1.42 | 0.86 |

Cold metrics are medians of 3 fresh server processes, from process launch to healthy and then for the first 25-document request. Server startup warmup was enabled and filesystem caches
were left in their normal OS-managed state. Warm metrics use 20 sequential requests per size after 2 warmups, with nearest-rank p95. Inputs are nested subsets of 50 distinct 300–500-character pilot passages paired with the same RuBQ question.
10 docs = 2,341 tokens (187–273 per pair), 25 docs = 5,761 tokens (187–275 per pair), 50 docs = 11,440 tokens (187–293 per pair).
macOS `/usr/bin/time -lp` recorded maximum resident size and peak physical footprint per process.
The table takes the largest value from the cold and warmed launches. Metal shares system memory.

See [the JSON report](rubq-pilot.json) for checksums, configuration and compact score statistics,
and [the benchmark guide](../benchmark/README.md) for the raw trace filenames and reproduction commands.
