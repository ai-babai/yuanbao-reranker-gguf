---
license: apache-2.0
thumbnail: https://huggingface.co/ai-babai/Yuanbao-Reranker-0.6B-GGUF/resolve/main/assets/social-preview.png
language:
  - ru
  - en
  - zh
  - multilingual
library_name: gguf
pipeline_tag: text-ranking
base_model: Yuanbao-Search/Yuanbao-Reranker-0.6B
base_model_relation: quantized
quantized_by: ai-babai
tags:
  - gguf
  - reranker
  - text-ranking
  - russian
  - llama-cpp
  - llama-server
  - node-llama-cpp
  - qmd
  - open-webui
  - rag
  - information-retrieval
  - qwen3
  - apple-silicon
  - q8_0
  - q4_k_m
inference: false
model-index:
- name: Yuanbao-Reranker-0.6B Q8_0
  results:
  - task:
      type: text-ranking
      name: Document reranking
    dataset:
      type: mteb/RuBQReranking
      name: RuBQ Horizon pilot (150 queries, 3,656 pairs)
      split: test
      revision: f2eac2f1f82445938af650c2a285a34dd77a16eb
    metrics:
    - name: nDCG@10
      type: ndcg_at_10
      value: 0.8479845659664136
    - name: MRR@10
      type: mrr_at_10
      value: 0.8407777777777777
    source:
      name: 150-query pilot and scoring protocol
      url: https://huggingface.co/ai-babai/Yuanbao-Reranker-0.6B-GGUF/blob/v0.1.1/results/rubq-pilot.md
- name: Yuanbao-Reranker-0.6B Q4_K_M
  results:
  - task:
      type: text-ranking
      name: Document reranking
    dataset:
      type: mteb/RuBQReranking
      name: RuBQ Horizon pilot (150 queries, 3,656 pairs)
      split: test
      revision: f2eac2f1f82445938af650c2a285a34dd77a16eb
    metrics:
    - name: nDCG@10
      type: ndcg_at_10
      value: 0.8487614236632546
    - name: MRR@10
      type: mrr_at_10
      value: 0.8390740740740741
    source:
      name: 150-query pilot and scoring protocol
      url: https://huggingface.co/ai-babai/Yuanbao-Reranker-0.6B-GGUF/blob/v0.1.1/results/rubq-pilot.md
- name: Yuanbao-Reranker-0.6B F16
  results:
  - task:
      type: text-ranking
      name: Document reranking
    dataset:
      type: mteb/RuBQReranking
      name: RuBQ Horizon pilot (150 queries, 3,656 pairs)
      split: test
      revision: f2eac2f1f82445938af650c2a285a34dd77a16eb
    metrics:
    - name: nDCG@10
      type: ndcg_at_10
      value: 0.8475904943681829
    - name: MRR@10
      type: mrr_at_10
      value: 0.8407777777777777
    source:
      name: 150-query pilot and scoring protocol
      url: https://huggingface.co/ai-babai/Yuanbao-Reranker-0.6B-GGUF/blob/v0.1.1/results/rubq-pilot.md
---

# Yuanbao-Reranker-0.6B GGUF: Q8_0 and Q4_K_M reranker for Russian search in QMD and llama.cpp

[Русская карточка](README.ru.md) ·
[Quick start](#quick-start) ·
[RuBQ results](results/rubq-pilot.md) ·
[Languages and runtimes](#languages-and-runtimes) ·
[QMD guide](docs/qmd.md) ·
[Open WebUI guide](docs/open-webui.md) ·
[For agents](AGENTS.md) ·
[GitHub](https://github.com/ai-babai/yuanbao-reranker-gguf) ·
[Original model](https://huggingface.co/Yuanbao-Search/Yuanbao-Reranker-0.6B)

![Yuanbao-Reranker-0.6B GGUF. For the question «Как отключить автопродление подписки?», llama-server with Q8_0 scored the subscription passage 0.943 and the password passage 0.0005. On 150 Russian RuBQ questions, Yuanbao Q8_0 ranked a relevant passage first for 113 and Qwen3-Reranker-0.6B Q8_0 for 102; nDCG@10 0.848 against 0.812.](https://huggingface.co/ai-babai/Yuanbao-Reranker-0.6B-GGUF/resolve/main/assets/yuanbao-reranker-header-en.png)

Tencent's multilingual Yuanbao-Reranker-0.6B in GGUF for local Russian search
and RAG. Stock `llama-server --reranking` serves it at `/v1/rerank`, and QMD
loads it through `models.rerank`. Tested on Apple Silicon with Metal and on
CPU. Independent ai-babai conversion, not an official Tencent release.

## Files

**Start with Q8_0.** It is the file tested in QMD and Open WebUI, and it kept
F16's top passage on all 150 RuBQ questions.

| File | Size | Use it for |
| --- | ---: | --- |
| `Yuanbao-Reranker-0.6B-Q8_0.gguf` | 0.64 GB | Default. Tested in QMD 2.9.0 and Open WebUI 0.13.4. |
| `Yuanbao-Reranker-0.6B-Q4_K_M.gguf` | 0.40 GB | 38% smaller than Q8_0 with similar RuBQ scores. The top passage changed on 10 of 150 questions. Not tested in QMD or Open WebUI. |
| `Yuanbao-Reranker-0.6B-F16.gguf` | 1.20 GB | Checking a conversion or comparing quantizations. |

`SHA256SUMS` lists the checksums. `RuBQ150-GGUF-benchmark.tar.gz` holds the
benchmark data behind the results below.

## Quick start

No account is needed. Download Q8_0 and its checksum from Hugging Face, then
start the server with the [tested llama.cpp build](docs/conversion.md) on your `PATH`.

```sh
base=https://huggingface.co/ai-babai/Yuanbao-Reranker-0.6B-GGUF/resolve/v0.1.1
mkdir -p models
curl -fL -o models/Yuanbao-Reranker-0.6B-Q8_0.gguf "$base/Yuanbao-Reranker-0.6B-Q8_0.gguf"
curl -fL -o models/SHA256SUMS "$base/SHA256SUMS"
(cd models && grep 'Q8_0.gguf' SHA256SUMS | shasum -a 256 -c -)
llama-server -m models/Yuanbao-Reranker-0.6B-Q8_0.gguf \
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
0.00046. With the same documents and the question «Где поменять пароль?», the
password passage moved to first place. For CPU-only serving, see the flags in
the [Open WebUI guide](docs/open-webui.md#start-the-reranker).

The same files through the Hugging Face CLI or, with a logged-in `gh`, the
GitHub release:

```sh
hf download ai-babai/Yuanbao-Reranker-0.6B-GGUF \
  Yuanbao-Reranker-0.6B-Q8_0.gguf SHA256SUMS --revision v0.1.1 --local-dir ./models
gh release download v0.1.1 --repo ai-babai/yuanbao-reranker-gguf \
  --pattern 'Yuanbao-Reranker-0.6B-Q8_0.gguf' --pattern SHA256SUMS --dir ./models
```

**For agents and scripts:** [manifest.json](manifest.json) lists the
release revision, filenames, sizes and SHA-256 hashes.
[results/rubq-pilot.json](results/rubq-pilot.json) holds the benchmark,
and [AGENTS.md](AGENTS.md) maps tasks to sources.

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
Against the Qwen3 Q8_0, Yuanbao Q8_0 gained +0.0355 nDCG@10, with a paired
bootstrap 95% interval of +0.0184 to +0.0536.

[Full results: ties, score agreement, latency and memory](results/rubq-pilot.md) ·
[Reproduce the benchmark](benchmark/README.md)

**Linux CPU.** On three AMD EPYC 7763 vCPUs, reranking 10 passages took a median of 11.71 s with Q4_K_M and 14.18 s with Q8_0. [CPU measurements for 10, 25 and 50 passages](results/linux-cpu.md) · [Raw timing samples](results/linux-cpu.json)

## Languages and runtimes

**Languages.** Tencent lists Chinese and English and describes the source model as multilingual. Its MLDR evaluation includes Arabic, Chinese, English, French, German, Hindi, Italian, Japanese, Korean, Portuguese, Russian, Spanish and Thai. The published MLDR number is an average across those 13 languages. We benchmarked these GGUFs on Russian RuBQ. In a separate CPU check, Q8_0 put the expected passage first on two hand-written queries each in English, Chinese and Russian. [Six requests and their scores](results/language-smoke.json) ·
[Tencent model card](https://huggingface.co/Yuanbao-Search/Yuanbao-Reranker-0.6B/blob/0101299a7937a016848d8d55b092f6e31cfa312d/README.md) ·
[Tencent benchmark task list](https://github.com/Yuanbao-Search/Yuanbao-Reranker/blob/3931311f46d3a815ad07b932d4796e54f77ff433/src/yuanbao_reranker/benchmarks.json)

| Runtime | Status with these GGUF files |
| --- | --- |
| llama.cpp `llama-server`, `/v1/rerank` | Tested at commit `5fddd0b` on Apple Metal and CPU. |
| node-llama-cpp 3.22.3 inside QMD 2.9.0 | Tested on Apple Metal, SDK and CLI. |
| Open WebUI 0.13.4, External reranker | Tested through llama-server on CPU. |
| LM Studio 0.4.25 (build 1) | Imports and loads Q8_0 as an LLM. The app API returned no ranking scores. The separate llama-server executable bundled in runtimes 2.44.0 and 2.82.0 ranked documents correctly. [Test and launch command](docs/lm-studio.md) |
| Transformers, vLLM, `yuanbao-reranker` package | Documented by Tencent for the original safetensors weights, not for GGUF. |

## QMD and Open WebUI

Where it fits:

```text
question → search: BM25, embeddings or QMD hybrid → candidate chunks
         → Yuanbao-Reranker-0.6B: /v1/rerank or QMD → chunks in score order
         → chat model context or search results
```

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

- The quality benchmark covers Russian RuBQ. The English and Chinese checks each cover two example queries.
- The ranking prompt is fixed in the GGUF. It uses an English web-search
  instruction, and `/v1/rerank` does not change it per request.
- Use the score to order candidates for one question. We did not test fixed
  score thresholds.
- The evaluation limits each input to 512 tokens. Longer passages can rank
  differently.
- QMD splits documents itself and blends the reranker score with search order,
  so the RuBQ gain does not carry over to QMD results one to one.

The two models tested together in Open WebUI are listed in [Russian RAG on llama.cpp](https://huggingface.co/collections/ai-babai/russian-rag-on-llamacpp-giga-embeddings-yuanbao-reranker-6b05c0c5c56ce9ebf2396add).

## License and attribution

Apache-2.0, as the original model. Converted from
[Yuanbao-Search/Yuanbao-Reranker-0.6B](https://huggingface.co/Yuanbao-Search/Yuanbao-Reranker-0.6B/tree/0101299a7937a016848d8d55b092f6e31cfa312d)
at revision `0101299`, which is derived from Qwen3. Modifications consist of the
reranking GGUF conversion, prompt configuration and quantization. See
[LICENSE](LICENSE) and [NOTICE](NOTICE). RuBQ labels are under CC BY-SA 4.0.
[Conversion recipe](docs/conversion.md)

**GGUF port, quantization, integrations and benchmarks:** Maksim Popkov (Максим Попков, ai-babai). [Cite this port](https://github.com/ai-babai/yuanbao-reranker-gguf/blob/main/CITATION.cff)
