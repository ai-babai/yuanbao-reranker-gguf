---
license: apache-2.0
language:
  - ru
  - en
  - zh
library_name: gguf
pipeline_tag: text-ranking
base_model: Yuanbao-Search/Yuanbao-Reranker-0.6B
base_model_relation: quantized
quantized_by: ai-babai
datasets:
  - mteb/RuBQReranking
tags:
  - gguf
  - reranker
  - text-ranking
  - russian
  - llama-cpp
  - llama-server
  - qmd
  - open-webui
  - rag
  - information-retrieval
  - qwen3
  - apple-silicon
  - q8_0
  - q4_k_m
inference: false
---

# Yuanbao-Reranker-0.6B GGUF: Q8_0 and Q4_K_M reranker for Russian search in QMD and llama.cpp

[Русская карточка](README.ru.md) ·
[RuBQ results](results/rubq-pilot.md) ·
[QMD guide](docs/qmd.md) ·
[Open WebUI guide](docs/open-webui.md) ·
[GitHub](https://github.com/ai-babai/yuanbao-reranker-gguf) ·
[Original model](https://huggingface.co/Yuanbao-Search/Yuanbao-Reranker-0.6B)

A local reranker for Russian-language search and RAG. Tencent's
Yuanbao-Reranker-0.6B converted to GGUF with rank pooling and an embedded
ranking prompt. Stock `llama-server --reranking` serves it at `/v1/rerank`, and
QMD loads it through `models.rerank`. Checked on Apple Silicon with Metal and on
CPU.

**Start with Q8_0.** It is the file tested in QMD and Open WebUI. On 150 Russian
RuBQ questions it scored 0.8480 nDCG@10, against 0.8124 for the
Qwen3-Reranker-0.6B Q8_0 that QMD uses by default, on the same llama.cpp build.

This is an independent ai-babai conversion, not an official Tencent release.
This repository and the GitHub repository are private for now.

```text
question → search: BM25, embeddings or QMD hybrid → candidate chunks
         → Yuanbao-Reranker-0.6B: /v1/rerank or QMD → chunks in score order
         → chat model context or search results
```

## Files

| File | Size | Use it for |
| --- | ---: | --- |
| `Yuanbao-Reranker-0.6B-Q8_0.gguf` | 0.64 GB | Default. Tested in QMD 2.9.0 and Open WebUI 0.13.4. |
| `Yuanbao-Reranker-0.6B-Q4_K_M.gguf` | 0.40 GB | 38% smaller than Q8_0 with similar RuBQ scores. The top passage changed on 10 of 150 questions. Not tested in QMD or Open WebUI. |
| `Yuanbao-Reranker-0.6B-F16.gguf` | 1.20 GB | Checking a conversion or comparing quantizations. |

`SHA256SUMS` lists the checksums. `RuBQ150-GGUF-benchmark.tar.gz` holds the
benchmark data behind the results below.

## Russian quality on RuBQ

150 public RuBQ questions and 3,656 question–passage pairs, following the
Horizon Labs protocol. Each GGUF ran on the same llama.cpp build through the
stock `/v1/rerank` endpoint with a 512-token input limit. Higher is better.

| Model | nDCG@10 | MRR@10 | Same top passage as F16 |
| --- | ---: | ---: | ---: |
| Yuanbao-Reranker-0.6B Q8_0 | 0.8480 | 0.8408 | 150 of 150 |
| Yuanbao-Reranker-0.6B Q4_K_M | 0.8488 | 0.8391 | 140 of 150 |
| Yuanbao-Reranker-0.6B F16 | 0.8476 | 0.8408 | baseline |
| Qwen3-Reranker-0.6B Q8_0, ggml-org, QMD default | 0.8124 | 0.7949 | — |

The original BF16 weights in PyTorch scored 0.8488 and 0.8419. The three Yuanbao files differ by at most 0.0012 nDCG@10. Q4_K_M changes which
passage comes first more often, so Q8_0 stays the default.

[Full results: ties, score agreement, latency and memory](results/rubq-pilot.md) ·
[Reproduce the benchmark](benchmark/README.md)

## Quick start with llama-server

Log in with `hf auth login` using an account that has access to this private
repository. Use llama.cpp at commit
[`5fddd0b`](https://github.com/ggml-org/llama.cpp/tree/5fddd0b99888a90260736e0f734fa8e160064e03),
the build tested with these files.

```sh
hf download ai-babai/Yuanbao-Reranker-0.6B-GGUF \
  Yuanbao-Reranker-0.6B-Q8_0.gguf SHA256SUMS \
  --revision v0.1.0 --local-dir ./models
(cd models && grep 'Q8_0.gguf' SHA256SUMS | shasum -a 256 -c -)
llama-server -m ./models/Yuanbao-Reranker-0.6B-Q8_0.gguf \
  --reranking --alias yuanbao --host 127.0.0.1 --port 8091
```

```sh
curl -sS http://127.0.0.1:8091/v1/rerank \
  -H 'Content-Type: application/json' \
  -d '{"model":"yuanbao","query":"Как отключить автопродление подписки?","documents":["Для изменения пароля откройте настройки безопасности.","Откройте раздел подписок и выключите автоматическое продление."],"top_n":2}'
```

The server returns the original document indices with their scores, highest
first. On Apple M4 Pro this request put the subscription passage (index 1) first
with a relevance score of 0.94275. The password passage (index 0) scored
0.00046.

## QMD and Open WebUI

**QMD.** Point `models.rerank` in the index configuration to the downloaded
file with an absolute path, then run `qmd trust`, `qmd update` and `qmd embed`.
QMD 2.9.0 created rank-pooling contexts for this file and reranked Russian
queries on Metal.

```yaml
models:
  rerank: "/absolute/path/to/Yuanbao-Reranker-0.6B-Q8_0.gguf"
```

**Open WebUI.** Enable **Hybrid Search**, choose **External** as the reranking
engine and enter the full `/v1/rerank` URL of the llama-server above. The
tested setup used Giga Embeddings for the dense search.

[QMD guide](docs/qmd.md) ·
[Open WebUI with Giga Embeddings](docs/open-webui.md) ·
[Giga Embeddings GGUF](https://huggingface.co/ai-babai/giga-embeddings-0826-480m-gguf)

## Limitations

- Russian quality was measured only on this RuBQ pilot. English and Chinese
  are listed by Tencent for the original model and were not tested here.
- The ranking prompt is fixed in the GGUF. It uses an English web-search
  instruction, and `/v1/rerank` does not change it per request.
- Use the score to order candidates for one question. We did not test fixed
  score thresholds.
- The evaluation limits each input to 512 tokens. Longer passages can rank
  differently.
- QMD splits documents itself and blends the reranker score with search order,
  so the RuBQ gain does not carry over to QMD results one to one.

## License and attribution

Apache-2.0, as the original model. Converted from
[Yuanbao-Search/Yuanbao-Reranker-0.6B](https://huggingface.co/Yuanbao-Search/Yuanbao-Reranker-0.6B/tree/0101299a7937a016848d8d55b092f6e31cfa312d)
at revision `0101299`, which is derived from Qwen3. Modifications consist of the
reranking GGUF conversion, prompt configuration and quantization. See
[LICENSE](LICENSE) and [NOTICE](NOTICE). RuBQ labels are under CC BY-SA 4.0.
[Conversion recipe](docs/conversion.md)
