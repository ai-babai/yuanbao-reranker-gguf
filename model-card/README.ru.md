# Yuanbao-Reranker-0.6B GGUF: реранкер для русского языка в QMD и llama.cpp

[English](README.md) ·
[Быстрый старт](#быстрый-старт) ·
[Результаты RuBQ](results/rubq-pilot.md) ·
[Языки и движки](#языки-и-движки) ·
[QMD](docs/qmd.md) ·
[Open WebUI](docs/open-webui.md) ·
[Для агентов](AGENTS.md) ·
[GitHub](https://github.com/ai-babai/yuanbao-reranker-gguf/blob/main/README.ru.md) ·
[Исходная модель](https://huggingface.co/Yuanbao-Search/Yuanbao-Reranker-0.6B)

![Yuanbao-Reranker-0.6B GGUF. На вопрос «Как отключить автопродление подписки?» llama-server с Q8_0 дал абзацу о подписке 0,943, абзацу о пароле 0,0005. На 150 русских вопросах RuBQ Yuanbao Q8_0 поставил релевантный фрагмент первым в 113 случаях, Qwen3-Reranker-0.6B Q8_0 — в 102; nDCG@10 0,848 против 0,812.](https://huggingface.co/ai-babai/Yuanbao-Reranker-0.6B-GGUF/resolve/main/assets/yuanbao-reranker-header-ru.png)

Многоязычный Yuanbao-Reranker-0.6B от Tencent в GGUF для локального поиска по
русским текстам и RAG. Штатный `llama-server --reranking` отдаёт его через
`/v1/rerank`, а QMD подключает через `models.rerank`. Проверено на Apple
Silicon с Metal и на CPU. Независимая конвертация ai-babai, а не официальный
релиз Tencent.

## Файлы

**Начинайте с Q8_0.** Этот файл проверен в QMD и Open WebUI и сохранил первый
фрагмент F16 во всех 150 вопросах RuBQ.

| Файл | Размер | Для чего |
| --- | ---: | --- |
| `Yuanbao-Reranker-0.6B-Q8_0.gguf` | 0,64 ГБ | Основной. Проверен в QMD 2.9.0 и Open WebUI 0.13.4. |
| `Yuanbao-Reranker-0.6B-Q4_K_M.gguf` | 0,40 ГБ | На 38% меньше Q8_0 при близких оценках на RuBQ. Первый фрагмент сменился в 10 вопросах из 150. В QMD и Open WebUI не проверялся. |
| `Yuanbao-Reranker-0.6B-F16.gguf` | 1,20 ГБ | Проверка конвертации и сравнение квантов. |

Контрольные суммы — в `SHA256SUMS`. В `RuBQ150-GGUF-benchmark.tar.gz` лежат
данные бенчмарка, по которым получены результаты ниже.

## Быстрый старт

Аккаунт не нужен. Скачайте Q8_0 и контрольную сумму с Hugging Face и запустите
сервер; [проверенная сборка llama.cpp](docs/conversion.md) должна быть в `PATH`.

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

Сервер возвращает исходные номера документов с оценками, лучший первым. На
Apple M4 Pro этот запрос поставил первым абзац о подписке (индекс 1) с оценкой
0,94275. Абзац о пароле (индекс 0) получил 0,00046. С теми же документами на
вопрос «Где поменять пароль?» первым стал абзац о пароле. Флаги для работы
только на CPU — в [руководстве по Open WebUI](docs/open-webui.md#start-the-reranker).

Те же файлы через Hugging Face CLI или, если `gh` авторизован, из релиза GitHub:

```sh
hf download ai-babai/Yuanbao-Reranker-0.6B-GGUF \
  Yuanbao-Reranker-0.6B-Q8_0.gguf SHA256SUMS --revision v0.1.1 --local-dir ./models
gh release download v0.1.1 --repo ai-babai/yuanbao-reranker-gguf \
  --pattern 'Yuanbao-Reranker-0.6B-Q8_0.gguf' --pattern SHA256SUMS --dir ./models
```

**Для агентов и скриптов:** в [manifest.json](manifest.json) — ревизия
релиза, имена файлов, размеры и SHA-256.
[results/rubq-pilot.json](results/rubq-pilot.json) — результаты
бенчмарка, [AGENTS.md](AGENTS.md) — какие файлы читать под задачу.

## Качество на русском: RuBQ

150 открытых вопросов RuBQ и 3 656 пар «вопрос — фрагмент» по протоколу Horizon
Labs. Все GGUF запускались на одной сборке llama.cpp через штатный `/v1/rerank`
с ограничением входа в 512 токенов. Больше — лучше.

| Модель | nDCG@10 | MRR@10 | Тот же первый фрагмент, что у F16 |
| --- | ---: | ---: | ---: |
| Yuanbao-Reranker-0.6B Q8_0 | 0,8480 | 0,8408 | 150 из 150 |
| Yuanbao-Reranker-0.6B Q4_K_M | 0,8488 | 0,8391 | 140 из 150 |
| Yuanbao-Reranker-0.6B F16 | 0,8476 | 0,8408 | база |
| Qwen3-Reranker-0.6B Q8_0, ggml-org, по умолчанию в QMD | 0,8124 | 0,7949 | — |

Исходные веса BF16 в PyTorch дали 0,8488 и 0,8419.
Три файла Yuanbao расходятся не больше чем на 0,0012 nDCG@10. Q4_K_M чаще
меняет первый фрагмент, поэтому основным остаётся Q8_0.
По сравнению с Qwen3 Q8_0 у Yuanbao Q8_0 nDCG@10 выше на 0,0355, парный
бутстреп даёт 95-процентный интервал от +0,0184 до +0,0536.

[Полные результаты: равные оценки, согласие оценок, задержка и память, англ.](results/rubq-pilot.md) ·
[Как воспроизвести бенчмарк, англ.](benchmark/README.md)

**Linux без GPU.** На трёх vCPU AMD EPYC 7763 медиана для 10 фрагментов составила 11,71 с с Q4_K_M и 14,18 с с Q8_0. [Замеры для 10, 25 и 50 фрагментов](results/linux-cpu.md) · [Исходные измерения](results/linux-cpu.json)

## Языки и движки

**Языки.** Tencent указывает китайский и английский и называет исходную модель многоязычной. В MLDR авторы оценивали арабский, китайский, английский, французский, немецкий, хинди, итальянский, японский, корейский, португальский, русский, испанский и тайский. Опубликованная оценка усреднена по этим 13 языкам. Мы измерили качество GGUF на русском RuBQ. В отдельной проверке на CPU Q8_0 поставил нужный фрагмент первым на двух составленных вручную вопросах на каждом из трёх языков — английском, китайском и русском. [Шесть запросов и ответы сервера](results/language-smoke.json) ·
[Карточка Tencent](https://huggingface.co/Yuanbao-Search/Yuanbao-Reranker-0.6B/blob/0101299a7937a016848d8d55b092f6e31cfa312d/README.md) ·
[Список задач оценки Tencent](https://github.com/Yuanbao-Search/Yuanbao-Reranker/blob/3931311f46d3a815ad07b932d4796e54f77ff433/src/yuanbao_reranker/benchmarks.json)

| Движок | Статус для этих GGUF |
| --- | --- |
| llama.cpp `llama-server`, `/v1/rerank` | Проверен на коммите `5fddd0b` с Apple Metal и на CPU. |
| node-llama-cpp 3.22.3 внутри QMD 2.9.0 | Проверен на Apple Metal, через SDK и CLI. |
| Open WebUI 0.13.4, внешний реранкер | Проверен через llama-server на CPU. |
| LM Studio 0.4.25 (build 1) | Импортирует и загружает Q8_0 как LLM. API приложения не вернул оценки. Отдельный llama-server из комплектов runtime 2.44.0 и 2.82.0 успешно ранжировал документы. [Проверка и команда запуска](docs/lm-studio.md) |
| Transformers, vLLM, пакет `yuanbao-reranker` | Tencent описывает их для исходных весов safetensors, не для GGUF. |

## QMD и Open WebUI

Где работает реранкер:

```text
вопрос → поиск: BM25, эмбеддинги или гибридный поиск QMD → кандидаты
       → Yuanbao-Reranker-0.6B: /v1/rerank или QMD → фрагменты по убыванию оценки
       → контекст для чат-модели или выдача поиска
```

**QMD.** Укажите в конфигурации индекса абсолютный путь к скачанному файлу в
`models.rerank`, затем выполните `qmd trust`, `qmd update` и `qmd embed`.
QMD 2.9.0 создал для этого файла контексты с rank pooling и переранжировал
русские запросы на Metal.

```yaml
models:
  rerank: "/absolute/path/to/Yuanbao-Reranker-0.6B-Q8_0.gguf"
```

**Open WebUI.** Включите **Hybrid Search**, выберите **External** как движок
ранжирования и укажите полный URL `/v1/rerank` сервера выше. В проверенной
связке векторный поиск выполнял Giga Embeddings.

[Руководство по QMD, англ.](docs/qmd.md) ·
[Open WebUI и Giga Embeddings, англ.](docs/open-webui.md) ·
[Giga Embeddings GGUF](https://huggingface.co/ai-babai/giga-embeddings-0826-480m-gguf)

## Ограничения

- Бенчмарк качества охватывает русский RuBQ. Для английского и китайского проверены по два примера.
- Промпт ранжирования зашит в GGUF. В нём английская инструкция для
  веб-поиска, и `/v1/rerank` не меняет её от запроса к запросу.
- Оценка нужна, чтобы упорядочить кандидатов для одного вопроса. Фиксированные
  пороги оценки мы не проверяли.
- В оценке вход ограничен 512 токенами. Более длинные фрагменты могут
  ранжироваться иначе.
- QMD сам режет документы и смешивает оценку реранкера с порядком поиска,
  поэтому выигрыш на RuBQ не переносится на выдачу QMD один к одному.

Обе проверенные вместе модели собраны в [коллекции для русского поиска в Open WebUI](https://huggingface.co/collections/ai-babai/russian-rag-on-llamacpp-giga-embeddings-yuanbao-reranker-6b05c0c5c56ce9ebf2396add).

## Лицензия и авторство

Apache-2.0, как у исходной модели. Конвертировано из
[Yuanbao-Search/Yuanbao-Reranker-0.6B](https://huggingface.co/Yuanbao-Search/Yuanbao-Reranker-0.6B/tree/0101299a7937a016848d8d55b092f6e31cfa312d)
ревизии `0101299`, основанной на Qwen3. Изменения: конвертация в GGUF для
ранжирования, настройка промпта и квантование. См. [LICENSE](LICENSE) и
[NOTICE](NOTICE). Метки RuBQ распространяются по CC BY-SA 4.0.
[Рецепт конвертации, англ.](docs/conversion.md)

**Автор порта GGUF, квантования, интеграций и бенчмарков — Максим Попков** (Maksim Popkov, ai-babai). [Как сослаться на порт](https://github.com/ai-babai/yuanbao-reranker-gguf/blob/main/CITATION.cff)
