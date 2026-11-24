#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 ARTIFACT_ROOT" >&2
    exit 2
fi

mkdir -p "$1/tools"
tools=$(cd "$1/tools" && pwd)
scripts=$(cd "$(dirname "$0")" && pwd)
llama="$tools/llama.cpp"
revision=5fddd0b99888a90260736e0f734fa8e160064e03

if [ ! -d "$llama/.git" ]; then
    git init "$llama"
    git -C "$llama" remote add origin https://github.com/ggml-org/llama.cpp.git
fi
if ! git -C "$llama" rev-parse --verify HEAD >/dev/null 2>&1; then
    git -C "$llama" fetch --depth 1 origin "$revision"
    git -C "$llama" checkout --detach "$revision"
fi
if [ "$(git -C "$llama" rev-parse HEAD)" != "$revision" ] ||
   [ -n "$(git -C "$llama" status --porcelain --untracked-files=no)" ]; then
    echo "Expected a clean llama.cpp checkout at $revision in $llama" >&2
    exit 1
fi

cmake -S "$llama" -B "$llama/build" -DCMAKE_BUILD_TYPE=Release \
    -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_APP=OFF \
    -DLLAMA_BUILD_TOOLS=ON -DLLAMA_BUILD_SERVER=ON \
    -DLLAMA_BUILD_UI=OFF -DLLAMA_USE_PREBUILT_UI=OFF
cmake --build "$llama/build" --target llama-server llama-quantize --parallel "${JOBS:-8}"

export UV_CACHE_DIR="$tools/uv-cache"
export UV_PYTHON_INSTALL_DIR="$tools/python"
venv="$tools/convert-venv"
if [ ! -x "$venv/bin/python" ]; then
    uv venv --python 3.12.11 "$venv"
fi
uv pip sync --python "$venv/bin/python" "$scripts/convert-requirements.txt"
