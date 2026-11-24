---
type: Project Guide
description: "Run the Yuanbao-Reranker-0.6B GGUF in QMD or as a local reranking service and reproduce its Russian RuBQ evaluation."
created: "2026-11-24"
---
# Yuanbao-Reranker-0.6B GGUF

Local reranking of Russian-language search results with Tencent's Yuanbao-Reranker-0.6B. Use the model after a text or vector search has selected candidate documents. The server returns their original indices and relevance scores in descending order. The GGUF uses the last-token yes/no classifier and the English web-search instruction used in our RuBQ evaluation.

## Local server

Download the weights with a GitHub account that has access to this repository. The draft is private. Point the server at the downloaded file.

```sh
gh release download v0.1.0 --repo ai-babai/yuanbao-reranker-gguf \
  --pattern 'Yuanbao-Reranker-0.6B-Q8_0.gguf' --dir ./models
llama-server -m ./models/Yuanbao-Reranker-0.6B-Q8_0.gguf \
  --reranking --host 127.0.0.1 --port 8091
```

```sh
curl -sS http://127.0.0.1:8091/v1/rerank \
  -H 'Content-Type: application/json' \
  -d '{"model":"yuanbao","query":"Как отключить автопродление подписки?","documents":["Для изменения пароля откройте настройки безопасности.","Откройте раздел подписок и выключите автоматическое продление."],"top_n":2}'
```

For QMD, set the reranker path under `models.rerank` in the index configuration. For Open WebUI, select the external reranker and enter the full `/v1/rerank` URL. See the verified integration guides for the complete configuration and examples.

- [QMD integration](docs/qmd.md)
- [Open WebUI with Giga Embeddings](docs/open-webui.md)
- [Create the GGUF files from the source weights](docs/conversion.md)

## Evaluation data

The pilot uses 150 public RuBQ questions and 3,656 query–passage pairs. Recreate it outside this checkout using the same dataset revision, seed, candidate order and 2,000-character document limit as the reference run.

```sh
uv run --script scripts/prepare_rubq.py /path/to/bench/rubq.parquet
```

The published Horizon comparison uses a 512-token total input budget and single newlines between instruction, query and passage. Tencent's example uses blank lines and a longer context. Run all GGUFs with the same input policy for a quality comparison. Serving a full document at another length can change the ranking. [Horizon evaluation code](https://huggingface.co/Horizon-Labs/multilingual-reranker-base/tree/7330f6d0b3f560af0c2b9a63820ea299a45fd91b/code/rerank) · [RuBQ dataset, CC BY-SA 4.0](https://huggingface.co/datasets/mteb/RuBQReranking/tree/f2eac2f1f82445938af650c2a285a34dd77a16eb)

## Attribution

Independent ai-babai conversion of the [Tencent Yuanbao Search checkpoint](https://huggingface.co/Yuanbao-Search/Yuanbao-Reranker-0.6B/tree/0101299a7937a016848d8d55b092f6e31cfa312d), derived from Qwen3. Modifications consist of the reranking GGUF conversion, prompt configuration and quantization. See [LICENSE](LICENSE) and [NOTICE](NOTICE). The comparison uses the [ggml-org Qwen3-Reranker-0.6B-Q8_0 GGUF](https://huggingface.co/ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF/tree/a02f48bb4f057028298c21fa033da2b30d7742d5).
