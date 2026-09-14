#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${PYTHON_BIN:-${project_root}/.venv/bin/python}"
build_root="${project_root}/build"
dist_root="${project_root}/dist"

if [[ ! -x "${python_bin}" ]]; then
    echo "Python executable not found: ${python_bin}" >&2
    echo "Set PYTHON_BIN or create .venv and install requirements-dev.txt." >&2
    exit 1
fi

if ! "${python_bin}" -c "import pygbag" >/dev/null 2>&1; then
    echo "Pygbag is not installed. Run:" >&2
    echo "  ${python_bin} -m pip install -r requirements-dev.txt" >&2
    exit 1
fi

# Some python.org macOS installs do not have their private CA bundle populated,
# even though the operating system bundle is available. Pygbag downloads its
# HTML template over HTTPS, so use the system bundle as a safe fallback.
if [[ -z "${SSL_CERT_FILE:-}" && -f /etc/ssl/cert.pem ]]; then
    export SSL_CERT_FILE=/etc/ssl/cert.pem
fi

mkdir -p "${build_root}" "${dist_root}"
temporary_root="$(mktemp -d "${build_root}/pygbag-build.XXXXXX")"
staging_dir="${temporary_root}/candy-monster-merge"
mkdir -p "${staging_dir}"
cleanup() {
    rm -rf "${temporary_root}"
}
trap cleanup EXIT

cp "${project_root}/main.py" "${staging_dir}/main.py"
cp "${project_root}/game.py" "${staging_dir}/game.py"
cp "${project_root}/game_logic.py" "${staging_dir}/game_logic.py"
cp "${project_root}/localization.py" "${staging_dir}/localization.py"

mkdir -p "${staging_dir}/assets"
for asset_dir in effects fonts monsters pieces; do
    cp -R "${project_root}/assets/${asset_dir}" "${staging_dir}/assets/${asset_dir}"
done

"${python_bin}" "${project_root}/scripts/prepare_web_assets.py" "${staging_dir}/assets"

"${python_bin}" -u -m pygbag \
    --build \
    --archive \
    --title "Candy Monster Merge" \
    --app_name "candy-monster-merge" \
    --ume_block 0 \
    "${staging_dir}"

archive="${staging_dir}/build/web.zip"
if [[ ! -f "${archive}" ]]; then
    echo "Pygbag did not create the expected archive: ${archive}" >&2
    exit 1
fi

preview_output="${build_root}/web-preview"
mkdir -p "${preview_output}"
rm -f "${preview_output}/candy-monster-merge.tar.gz"
cp "${staging_dir}/build/web/index.html" "${preview_output}/index.html"
cp "${staging_dir}/build/web/favicon.png" "${preview_output}/favicon.png"
cp "${staging_dir}/build/web/candy-monster-merge.apk" "${preview_output}/candy-monster-merge.apk"
if [[ -f "${staging_dir}/build/web/candy-monster-merge.tar.gz" ]]; then
    cp "${staging_dir}/build/web/candy-monster-merge.tar.gz" "${preview_output}/candy-monster-merge.tar.gz"
fi

output="${dist_root}/candy-monster-merge-web.zip"
cp "${archive}" "${output}"
echo "Created ${output}"
echo "Local preview files: ${preview_output}"
