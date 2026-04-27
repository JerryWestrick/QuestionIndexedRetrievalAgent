#!/usr/bin/env bash
# try-eu-ai-act.sh — install the EU AI Act QIRA corpus into a fresh
# keprompt project so you can ask an LLM about the EU AI Act in 2 minutes.
#
# Usage:
#   curl -L https://github.com/JerryWestrick/QuestionIndexedRetrievalAgent/raw/main/examples/eu-ai-act/try-eu-ai-act.sh | bash
#
# Or download and run:
#   curl -LO https://github.com/JerryWestrick/QuestionIndexedRetrievalAgent/raw/main/examples/eu-ai-act/try-eu-ai-act.sh
#   bash try-eu-ai-act.sh
#
# The script creates ./eu-ai-act-test/ in the current directory, builds
# a Python venv inside it, installs keprompt + qira dependencies, downloads
# the EU AI Act corpus, and writes a demo prompt. It does not export your
# API key and does not run the LLM — final instructions are printed at the end.

set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-eu-ai-act-test}"
CORPUS_URL="https://github.com/JerryWestrick/QuestionIndexedRetrievalAgent/raw/main/corpus/eu-ai-act.zip"
PYTHON="${PYTHON:-python3}"

say() { printf '\n\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!! %s\033[0m\n' "$*" >&2; }
die() { printf '\033[1;31m!! %s\033[0m\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

command -v "$PYTHON" >/dev/null 2>&1 || die "$PYTHON not found on PATH. Install Python 3.12+."
command -v curl >/dev/null 2>&1 || die "curl not found on PATH."
command -v unzip >/dev/null 2>&1 || die "unzip not found on PATH."

PY_VER=$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
case "$PY_VER" in
    3.12|3.13|3.14|3.15) ;;
    *) die "Python 3.12+ required, found $PY_VER." ;;
esac

# ---------------------------------------------------------------------------
# Project directory + venv
# ---------------------------------------------------------------------------

if [ -e "$PROJECT_DIR" ] && [ ! -d "$PROJECT_DIR" ]; then
    die "$PROJECT_DIR exists and is not a directory."
fi

mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"
say "Project directory: $(pwd)"

if [ ! -d .venv ]; then
    say "Creating Python venv (.venv)"
    "$PYTHON" -m venv .venv
else
    say "Reusing existing .venv"
fi

# Activate the venv for the rest of the script. The user will need to
# re-activate it in their own shell after the script exits.
# shellcheck disable=SC1091
source .venv/bin/activate

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

say "Installing Python packages (keprompt, faiss-cpu, model2vec)"
pip install --quiet --upgrade pip
pip install --quiet keprompt faiss-cpu model2vec

# ---------------------------------------------------------------------------
# keprompt init (creates prompts/, prompts/functions/, etc.)
# ---------------------------------------------------------------------------

if [ ! -d prompts/functions ]; then
    say "Initializing keprompt project"
    keprompt init
else
    say "keprompt project already initialized"
fi

# ---------------------------------------------------------------------------
# Download + extract corpus
# ---------------------------------------------------------------------------

ZIP_TMP="$(mktemp -t eu-ai-act-XXXXXX.zip)"
trap 'rm -f "$ZIP_TMP"' EXIT

say "Downloading EU AI Act corpus zip"
curl -fL --progress-bar -o "$ZIP_TMP" "$CORPUS_URL" \
    || die "Download failed. URL: $CORPUS_URL"

say "Extracting corpus into prompts/functions/"
unzip -oq "$ZIP_TMP" -d prompts/functions/
chmod +x prompts/functions/qira

# ---------------------------------------------------------------------------
# Initialize qira (writes prompts/functions/qira.prompt)
# ---------------------------------------------------------------------------

say "Generating qira.prompt"
prompts/functions/qira --initialize

# ---------------------------------------------------------------------------
# Demo prompt
# ---------------------------------------------------------------------------

DEMO_PROMPT="prompts/eu-ai-act-demo.prompt"
if [ ! -f "$DEMO_PROMPT" ]; then
    say "Writing demo prompt: $DEMO_PROMPT"
    cat > "$DEMO_PROMPT" <<'PROMPT'
.prompt "name":"eu-ai-act-demo", "version":"1.0", "params":{"model":"openai/gpt-4o-mini", "question":"What AI practices does the EU AI Act prohibit?"}
.functions qira.*
.system You are a helpful assistant. Use qira_search and qira_read to ground answers in the available corpora. Cite section IDs (e.g. eu-ai-act:3.1).
.include prompts/functions/qira.prompt
.user <<question>>
.exec
PROMPT
else
    say "Demo prompt already exists: $DEMO_PROMPT"
fi

# ---------------------------------------------------------------------------
# Done — final instructions
# ---------------------------------------------------------------------------

printf '\n\033[1;32m==> Setup complete.\033[0m\n\n'
cat <<EOF
The EU AI Act corpus is installed in:
    $(pwd)/prompts/functions/qira-corpus/eu-ai-act/

To run the demo:

  cd $(pwd)
  source .venv/bin/activate
  export OPENAI_API_KEY=sk-...     # or ANTHROPIC_API_KEY, CEREBRAS_API_KEY, etc.
  keprompt chat new eu-ai-act-demo

To ask a different question:

  keprompt chat new eu-ai-act-demo --set question="Who must register a high-risk AI system?"

To switch model, edit the model field in:
  $(pwd)/$DEMO_PROMPT

The first qira_search call will download the Model2Vec embedding model
(~30 MB) from HuggingFace. After that, calls are local and offline.

EOF
