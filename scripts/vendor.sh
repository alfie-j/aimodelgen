#!/usr/bin/env bash
# Re-download the front-end libraries (already committed in app/static/vendor) from npm.
set -euo pipefail
V="$(cd "$(dirname "$0")/.." && pwd)/app/static/vendor"; T="$(mktemp -d)"; mkdir -p "$V/fonts"
(cd "$T" && npm pack --silent marked@12.0.2 katex@0.16.11 >/dev/null && for f in *.tgz; do mkdir "${f%.tgz}" && tar -xzf "$f" -C "${f%.tgz}"; done)
cp "$T"/marked-12.0.2/package/marked.min.js "$V/"
cp "$T"/katex-0.16.11/package/dist/katex.min.{js,css} "$V/"
cp "$T"/katex-0.16.11/package/dist/fonts/*.woff2 "$V/fonts/"
rm -rf "$T"; echo "vendored into $V"
