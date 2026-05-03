#!/usr/bin/env bash
# Rebuild QIRA_Article.pdf from QIRA_Article.md.
#
# Run this whenever QIRA_Article.md changes and commit the resulting PDF
# alongside the .md change. The PDF lives in the repo so readers without
# a markdown renderer can still get a clean copy.
#
# Requires: pandoc + a TeX Live distribution providing xelatex (Debian/Ubuntu:
#   apt install pandoc texlive-xetex texlive-fonts-recommended).

set -euo pipefail

cd "$(dirname "$0")/.."

pandoc QIRA_Article.md \
  -o QIRA_Article.pdf \
  --pdf-engine=xelatex \
  --toc \
  --toc-depth=2 \
  -V geometry:margin=1in \
  -V mainfont="DejaVu Serif" \
  -V monofont="DejaVu Sans Mono" \
  -V sansfont="DejaVu Sans" \
  -V colorlinks=true \
  -V linkcolor=blue \
  -V urlcolor=blue \
  -V toccolor=black \
  --highlight-style=tango

echo "Wrote QIRA_Article.pdf ($(wc -c < QIRA_Article.pdf) bytes, $(pdfinfo QIRA_Article.pdf 2>/dev/null | awk '/^Pages:/ {print $2}') pages)"