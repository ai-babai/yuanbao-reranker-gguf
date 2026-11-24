---
type: Integration Guide
description: Connect Yuanbao GGUF to Open WebUI through llama-server and verify hybrid retrieval with Giga Embeddings.
created: "2026-11-24"
---

# Yuanbao reranking in Open WebUI

Open WebUI can use Yuanbao as an external reranker. Its hybrid search combines
BM25 with dense embeddings to select candidates. Open WebUI sends those chunks
to llama-server for scoring and passes the highest-scoring chunks to the chat
model. The embedding, reranking, and chat endpoints are configured separately.
[Open WebUI RAG reference](https://docs.openwebui.com/troubleshooting/rag/)

## Start the reranker

Run this from the artifact directory that contains `weights/`. Use the
`llama-server` build documented for this port.

```sh
llama-server \
  -m weights/Yuanbao-Reranker-0.6B-Q8_0.gguf \
  --alias yuanbao-reranker-0.6b-q8_0 \
  --reranking --host 127.0.0.1 --port 18122 \
  -c 2048 -b 1024 -ub 1024 -np 1
```

For a CPU-only run, add `--device none --no-op-offload -ngl 0`. Check that
`GET /health` succeeds before sending a request. This example asks for the
better of two candidate passages.

```sh
curl -fsS http://127.0.0.1:18122/v1/rerank \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "yuanbao-reranker-0.6b-q8_0",
    "query": "Кто снял фильм Список Шиндлера?",
    "documents": [
      "Оскар Шиндлер был немецким предпринимателем.",
      "Фильм «Список Шиндлера» снял Стивен Спилберг."
    ],
    "top_n": 1
  }'
```

In the response, `results[].index` is a zero-based position in the original
`documents` array and `results[].relevance_score` is the score. Results are
sorted by descending score. The example returned index 1 with score
0.999825. In Open WebUI 0.13.4, each external request uses
`top_n` equal to the number of candidates. Open WebUI then applies its own
**Top K Reranker** to select the final chunks.
[External reranker API settings](https://docs.openwebui.com/reference/env-configuration/#rag_external_reranker_url)

## Configure Open WebUI

In **Admin Panel → Settings → Documents**, enable **Hybrid Search** and select
**External** as the reranking engine. Use `yuanbao-reranker-0.6b-q8_0` for the
model and `http://127.0.0.1:18122/v1/rerank` for the complete URL when both
processes run on the same host. If Open WebUI runs in a container, use an
address reachable from that container. If the server requires authentication,
supply its API key in the external reranker settings.

Equivalent environment settings for a fresh Open WebUI instance follow.

```sh
export ENABLE_RAG_HYBRID_SEARCH=true
export RAG_HYBRID_BM25_WEIGHT=0.5
export RAG_RERANKING_ENGINE=external
export RAG_RERANKING_MODEL=yuanbao-reranker-0.6b-q8_0
export RAG_EXTERNAL_RERANKER_URL=http://127.0.0.1:18122/v1/rerank
export RAG_TOP_K=4
export RAG_TOP_K_RERANKER=2
```

For a local check with short files, set `RAG_FULL_CONTEXT=false` and
`RAG_FULL_TEXT_CHAR_THRESHOLD=0` so the chat retrieves chunks. Set
`ENABLE_RETRIEVAL_QUERY_GENERATION=false` if you need the exact user question
to reach the retriever and reranker. Persisted admin settings can take
precedence over environment variables on an existing instance.
[Open WebUI configuration precedence](https://docs.openwebui.com/reference/env-configuration/#important-note-on-configvar-environment-variables)

### Use Giga Embeddings for dense retrieval

This integration was verified with the Giga Embeddings 0826 480M Q8_0 GGUF and
actual 1,024-dimensional embeddings. Start a separate llama-server from the
directory containing the Giga model. Keep the model's mean pooling and L2
normalization defaults. Follow the model card for a compatible llama.cpp
build. [Giga Embeddings model card](https://huggingface.co/ai-babai/giga-embeddings-0826-480m-gguf)

```sh
llama-server \
  -m giga-embeddings-0826-480m-q8_0.gguf \
  --alias giga-embeddings-0826-480m-q8_0 \
  --embeddings --host 127.0.0.1 --port 18123 \
  -c 2048 -b 2048 -ub 2048 -np 1 \
  --cache-type-k f32 --cache-type-v f32 --flash-attn auto
```

Select **OpenAI** as the embedding engine with the base URL
`http://127.0.0.1:18123/v1` and model `giga-embeddings-0826-480m-q8_0`. The base
URL ends at `/v1` because Open WebUI appends `/embeddings`. Use the query
prefix below and leave the content prefix empty, so only queries get the
retrieval instruction. Index or reindex the knowledge files with this engine.

```sh
export RAG_EMBEDDING_ENGINE=openai
export RAG_OPENAI_API_BASE_URL=http://127.0.0.1:18123/v1
export RAG_EMBEDDING_MODEL=giga-embeddings-0826-480m-q8_0
export RAG_EMBEDDING_QUERY_PREFIX="$(printf 'Instruct: Given a query, retrieve relevant passages\nQuery: ')"
```

## Verify a chat with documents

To start a disposable instance, run these commands in an empty directory
outside the checkout after exporting the retrieval settings above. Point the
chat connection to a separate local OpenAI-compatible chat server. The run
below used Qwen2.5-3B-Instruct Q4_K_M for generation.

```sh
UV_CACHE_DIR="$PWD/uv-cache" uv venv --python 3.12 .venv
UV_CACHE_DIR="$PWD/uv-cache" uv pip install --python .venv/bin/python 'open-webui==0.13.4'
DATA_DIR="$PWD/data" VECTOR_DB=chroma OFFLINE_MODE=true \
  ENABLE_OLLAMA_API=false OPENAI_API_BASE_URLS=http://127.0.0.1:18126/v1 \
  .venv/bin/open-webui serve --host 127.0.0.1 --port 18121
```

1. Connect a chat model in Open WebUI and add Russian text documents to a
   knowledge collection. Wait for processing to finish.
2. Attach the collection to a chat in retrieval mode and ask a question the
   documents can answer. Open the returned sources to see the selected chunks.
3. Check for a successful `POST /v1/rerank` in the reranker server trace and
   `ExternalReranker:predict:model yuanbao-reranker-0.6b-q8_0` in Open WebUI.
   Check the returned indices and scores if the final sources are unexpected.

The isolated run used the same application API as chat,
`POST /api/chat/completions`, with
`files: [{"type": "collection", "id": "<knowledge-id>"}]`. It indexed six
public Russian passages from the `test_query1021` candidate list into 14
Chroma chunks using a chunk size of 220 characters and overlap of 25. For
«Кто снял фильм Список Шиндлера?», the dense/BM25 candidate union contained
seven chunks. Yuanbao moved input positions 2 and 4 to the top with scores
0.993432 and 0.798043. Open WebUI returned exactly those chunks as chat
sources. A direct replay returned the same results and setting `top_n=2`
returned just those two positions. A BM25-only control omitted the
top-ranked film passage. [RuBQ reranking dataset](https://huggingface.co/datasets/mteb/RuBQReranking)

The chat model answered «Фильм "Список Шиндлера" снят режиссером Стивеном
Спилбергом [1].» using this RAG template. The initial Qwen2.5 0.5B run copied
the example answer in the default template even though retrieval returned
the expected sources. With Qwen2.5 3B, the birth-year question also returned
the correct year with a citation. The chat model repeated a third question
about who played Schindler after retrieval switched to two Neeson passages.

```text
Ответь на вопрос по источникам одним предложением на русском. Укажи номер источника в квадратных скобках. Если в источниках нет ответа, скажи об этом.

Источники:
[context]

Вопрос: [query]
Ответ:
```

Tested with Open WebUI 0.13.4, Chroma 1.5.9, Python 3.12.11, and llama-server
1.0.0-dev at `5fddd0b99888a90260736e0f734fa8e160064e03` for Yuanbao. The
embedding server was llama-server 0.3.0-dev at `e750b887a`.
