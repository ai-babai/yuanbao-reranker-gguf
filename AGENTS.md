---
type: Agent Instructions
description: How to select the GGUF, serve reranking requests and verify claims about the port.
created: "2026-11-24"
---
# Using this reranker

Read [manifest.json](manifest.json) for the release revision, default GGUF filename, sizes, SHA-256 hashes and upstream revision. The default Q8_0 file works in stock llama.cpp with `--reranking`. Send a query and candidate documents to `POST /v1/rerank`. Each returned index refers to the original document array.

| Task | Source |
| --- | --- |
| Run the model and check an example response | [Quick start](README.md) |
| Reproduce quality and latency results | [Benchmark guide](benchmark/README.md) and [machine-readable report](results/rubq-pilot.json) |
| Configure a search client | [QMD](docs/qmd.md), [Open WebUI](docs/open-webui.md), [LM Studio compatibility](docs/lm-studio.md) |
| Rebuild and verify weight files | [Conversion guide](docs/conversion.md) and [release checksums](SHA256SUMS) |
| Cite this port and distinguish upstream credit | [CITATION.cff](CITATION.cff), [NOTICE](NOTICE) and [LICENSE](LICENSE) |

The RuBQ results apply to the published 150-query pilot. Consult its JSON before comparing variants. When reproducing benchmarks, keep weights, datasets, caches and raw runs outside the source checkout.
