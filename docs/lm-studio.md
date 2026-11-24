---
type: Integration Report
description: Import, load, and API checks for Yuanbao Q8_0 in LM Studio, plus a working standalone reranking command.
created: "2026-11-24"
---
# Yuanbao in LM Studio

LM Studio 0.4.25 Build 1 imports and loads `Yuanbao-Reranker-0.6B-Q8_0.gguf` as an LLM. Its application server did not expose document reranking. The same llama.cpp runtime shipped as an LM Studio extension returned real rerank scores when launched separately with `--reranking`.

The check used macOS 15.8.1 on Apple M4 Pro and `lms` commit `69d945a`. LM Studio automatically downloaded and selected `llama.cpp-mac-arm64-apple-metal-advsimd@2.82.0` in the disposable profile. The GGUF SHA-256 was `4c051aa4d4ea7276fdbef78b1a97869929b241f9812ffffdeeff35b431473912`.

## Application server check

These commands ran against a disposable LM Studio profile and models directory. On this Mac, a fresh `HOME` alone still resolved the ordinary models path. The test set `downloadsFolder` in the disposable profile and checked the destination with `lms import --dry-run` before importing. For a fresh local check, set `GGUF_ROOT` to your artifact directory and use a free loopback port. [LM Studio CLI import](https://lmstudio.ai/docs/cli/local-models/import) · [Server start](https://lmstudio.ai/docs/cli/serve/server-start)

```sh
lms import "$GGUF_ROOT/weights/Yuanbao-Reranker-0.6B-Q8_0.gguf" \
  --symbolic-link --user-repo yuanbao-smoke/yuanbao-reranker-gguf --yes
lms ls --json
lms ls --embedding --json
lms server start --bind 127.0.0.1 --port 18139
lms load yuanbao-reranker --identifier yuanbao-smoke-q8 \
  --context-length 512 --gpu max --ttl 180 --yes
lms ps --json
curl -fsS http://127.0.0.1:18139/api/v1/models
```

`lms ls` and the native REST model list reported `type: llm`, architecture `qwen3`, 596M parameters and Q8_0. The embedding-only list was empty. Both `lms ps` and the REST model list showed the active `yuanbao-smoke-q8` instance with a 512-token context.

| Request to LM Studio | Observed result |
| --- | --- |
| `POST /v1/rerank`, two Russian queries with three documents and `top_n: 2` | HTTP 200 with `{"error":"Unexpected endpoint or method. (POST /v1/rerank)"}` for both |
| `POST /api/v1/rerank` | HTTP 404 with an unexpected-endpoint error |
| `POST /v1/embeddings`, with an array of Russian texts | HTTP 400, `No models loaded`, while the LLM instance was active |
| `POST /v1/chat/completions` and `POST /v1/completions` | HTTP 200 with generated tokens (`1` and ` Для` respectively). Neither result contained document scores or indices. |

The other route probes (`/rerank`, `/api/v0/rerank`, `/v1/ranking` and `/v1/decisions`) also returned unexpected-endpoint errors. The CLI has no rerank command. The documented REST model types are `llm`, `embedding` and `decision`. The decision API is documented for TypeSafe System One. LM Studio's documented `model.yaml` can override model metadata and load or inference defaults, but it exposes no reranker domain or route for this GGUF. The application results establish the boundary directly. [REST model types](https://lmstudio.ai/docs/developer/rest/list) · [OpenAI-compatible endpoints](https://lmstudio.ai/docs/developer/openai-compat) · [TypeSafe decisions](https://lmstudio.ai/docs/developer/openai-compat/decisions) · [Model configuration](https://lmstudio.ai/docs/app/modelyaml)

## Standalone reranking with the runtime binary

Use `lms runtime ls` to see the installed versions. The CLI can fetch the newer extension with `lms runtime get 'llama.cpp@2.82.0'`. On this Mac the already-installed `2.44.0` also worked, so either of these executable paths can be used when the corresponding extension is installed.

```sh
LLAMA_SERVER="$HOME/.lmstudio/extensions/backends/llama.cpp-mac-arm64-apple-metal-advsimd-2.82.0/llama-server"
# For the existing 2.44.0 extension, use this path instead
# LLAMA_SERVER="$HOME/.lmstudio/extensions/backends/llama.cpp-mac-arm64-apple-metal-advsimd-2.44.0/llama-server"
```

The `2.82.0` binary reported `1.0.0-dev`, build 1, commit `1094646`. The `2.44.0` binary reported `0.4.1-dev`, build 1, commit `42916d8`. Launching either manually starts a separate llama.cpp service with its own port and configuration.

```sh
"$LLAMA_SERVER" -m "$GGUF_ROOT/weights/Yuanbao-Reranker-0.6B-Q8_0.gguf" \
  --reranking --alias yuanbao-smoke-q8 --host 127.0.0.1 --port 18140 \
  --ctx-size 512 --parallel 1 --n-gpu-layers 99
```

In another terminal, send both queries against the same document order.

```sh
for question in 'Как отключить автопродление подписки?' 'Как изменить пароль?'; do
  jq -n --arg query "$question" '{
    model: "yuanbao-smoke-q8",
    query: $query,
    documents: [
      "Для изменения пароля откройте настройки безопасности.",
      "Откройте раздел подписок и выключите автоматическое продление.",
      "Историю покупок можно скачать в настройках платежей."
    ],
    top_n: 2
  }' | curl -fsS http://127.0.0.1:18140/v1/rerank \
    -H 'Content-Type: application/json' --data-binary @-
  printf '\n'
done
```

Both runtime versions returned HTTP 200 with identical scores and zero-based indices for these two requests. Each list contained two results in descending `relevance_score` order.

| Query | First result index and score | Second result index and score |
| --- | --- | --- |
| Как отключить автопродление подписки? | 1 · 0.94274849 | 2 · 0.00131015 |
| Как изменить пароль? | 0 · 0.46566889 | 1 · 0.00015888 |

For a separate stock llama.cpp installation, see the [local server example](../README.md).

## Giga Embeddings and Hugging Face discovery

The historical Giga release record (`29c40b4` in `giga-embeddings-gguf`) documents changes to **GGUF metadata** in Giga 480M and 3B. It prefixed `general.name` with `Qwen3 Embedding` and added `general.description` without changing tensors. LM Studio 0.4.25 then classified fresh imports as Text Embedding, and its public embeddings route returned genuine 1024- and 2048-dimensional vectors respectively. Both verified Giga HF revision file lists have no `model.yaml`. The `lmstudio` card tag was for discovery. LM Studio Hub's separate `model.yaml` mechanism describes catalog entries. [480M release revision](https://huggingface.co/ai-babai/giga-embeddings-0826-480m-gguf/tree/34da7d5d7e8dd454e7f40bc5dca98b00a5086c3d) · [3B release revision](https://huggingface.co/ai-babai/giga-embeddings-0826-3b-gguf/tree/e292a35c49bbab4f53842588b59c37628d362321) · [LM Studio Hub model.yaml publishing](https://lmstudio.ai/docs/app/modelyaml/publish)

For a Yuanbao GGUF card, use `pipeline_tag: text-ranking`, `library_name: gguf`, `license: apache-2.0`, and `base_model: Yuanbao-Search/Yuanbao-Reranker-0.6B` with `base_model_relation: quantized`. Descriptive tags such as `reranker`, `qwen3`, and `rag` describe valid uses. Leave out `lmstudio` as a compatibility claim. The HF task and library fields describe the artifact and do not change how the LM Studio application loads it. [HF Text Ranking task](https://huggingface.co/tasks/text-ranking) · [HF model card reference](https://huggingface.co/docs/hub/en/model-cards) · [Upstream Yuanbao](https://huggingface.co/Yuanbao-Search/Yuanbao-Reranker-0.6B)

Local evidence under `$GGUF_ROOT/integrations/lm-studio/` includes `lms-ls.json`, `lms-ps.json`, `api-models-after.json`, `http-summary.log`, the raw request and response JSON files, `backend-version.log`, `standalone.log`, `standalone-2.44.log`, and `verification.log`.
