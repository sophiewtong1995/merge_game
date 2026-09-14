#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${PYTHON_BIN:-${project_root}/.venv/bin/python}"
app_dir="${project_root}/build/candy-monster-merge"
server_port="${PORT:-8000}"

if [[ ! -x "${python_bin}" ]]; then
    echo "Python executable not found: ${python_bin}" >&2
    exit 1
fi

if [[ ! -f "${app_dir}/main.py" ]]; then
    "${project_root}/scripts/build_web.sh"
fi

# The Pygbag server proxies and caches its WebAssembly dependencies. A plain
# python -m http.server cannot do that on a browser's first uncached load.
if [[ -z "${SSL_CERT_FILE:-}" && -f /etc/ssl/cert.pem ]]; then
    export SSL_CERT_FILE=/etc/ssl/cert.pem
fi

echo "Open http://localhost:${server_port}"
exec "${python_bin}" -u -m pygbag \
    --title "Candy Monster Merge" \
    --app_name "candy-monster-merge" \
    --ume_block 0 \
    --port "${server_port}" \
    "${app_dir}"
