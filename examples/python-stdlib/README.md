# Example: Python Standard Library Corpus

Build a QIRA corpus from the Python standard library documentation. This is a complete, working example that demonstrates the full QI (Question Indexing) pipeline — from source documents to a searchable corpus.

## What This Produces

A corpus directory ready for the QIRA runtime (`qira_search` / `qira_read`):

```
output/python-stdlib/
  python-stdlib.db       # SQLite — sections with pre-formatted markdown
  chroma/                # ChromaDB — question vector index
  corpus.md              # Corpus identity for qira --initialize
```

## Prerequisites

- Python 3.12+
- QIRA venv with dependencies: `chromadb`, `docutils`
- [keprompt](https://github.com/your/keprompt) installed with a Cerebras API key
- CPython documentation source (RST files)

## Step-by-Step

### 1. Get the Python Documentation Source

The Python standard library docs are RST (reStructuredText) files in the CPython repository. We only need the `Doc/library/` directory.

```bash
cd /tmp
git clone --depth 1 --filter=blob:none --sparse https://github.com/python/cpython.git cpython-docs
cd cpython-docs
git sparse-checkout set Doc/library
```

This gives you ~330 `.rst` files — one per module/topic.

### 2. Understand the Source Format

Python docs use Sphinx-flavored RST. The structure is explicit:

```rst
:mod:`json` --- JSON encoder and decoder
=========================================

.. module:: json
   :synopsis: Encode and decode the JSON format.

Basic Usage
-----------

.. function:: dump(obj, fp, *, indent=None, sort_keys=False)

   Serialize *obj* as a JSON formatted stream to *fp*.

   :param object obj: The Python object to be serialized.
   :param fp: The file-like object.
```

Key structural elements:
- **Heading underlines** (`===`, `---`, `~~~`) define section hierarchy
- **Directives** (`.. function::`, `.. class::`, `.. method::`, `.. exception::`) mark API elements
- **Roles** (`:func:`, `:class:`, `:mod:`, `:ref:`) are cross-references
- **Param fields** (`:param type name:`) document parameters

This is a best-case source format — more structure than we even need.

### 3. Parse RST → Section Tree (Format-Specific Adapter)

The RST adapter does two things:

**3a. Parse** — use `docutils` to parse each `.rst` file into a document tree (AST). The tree gives us sections, headings, directives, and cross-references as structured nodes — no regex, no string hacking.

**3b. Convert to markdown** — walk the AST, emit markdown preserving the section hierarchy. RST directives become markdown headings and content blocks. Cross-reference roles (`:func:`json.dumps``) are preserved for rewriting in step 5.

After this step, every module is a markdown document with a clean section tree. This is the **only format-specific step** — everything downstream is shared infrastructure.

### 4. Organize Sections

Assign hierarchical IDs and build breadcrumbs:

```
python-stdlib:1        json — JSON encoder and decoder
python-stdlib:1.1      Basic Usage
python-stdlib:1.1.1    json.dump
python-stdlib:1.1.2    json.dumps
python-stdlib:1.2      Decoders
python-stdlib:1.2.1    json.JSONDecoder
python-stdlib:2        datetime — Date and time types
python-stdlib:2.1      datetime.date
...
```

Each module gets a top-level number. Sections within the module get dot-separated sub-numbers. Breadcrumbs are built from the heading hierarchy: `Python Standard Library > json > Basic Usage > json.dump`.

Determine readable units — the depth at which sections are self-contained. For Python docs, individual functions/classes/methods are typically the right level. Deeper sub-sections (parameter lists, examples) become inline content within their parent's `read_entry`.

### 5. Rewrite Cross-References

Convert all RST cross-references to full QIRA section IDs:

- `:func:`json.dumps`` → `python-stdlib:1.1.2`
- `:class:`JSONDecoder`` → `python-stdlib:1.2.1`
- `:mod:`pickle`` → `python-stdlib:45` (or left as-is if the target module isn't in the corpus)

After this step, the LLM can act on any cross-reference immediately — just pass the ID to `qira_read`.

### 6. Generate Questions (LLM Call)

This is the core of QI — the step that makes QIRA different from RAG.

For each section, an LLM reads the content **in its full context** (parent headings, breadcrumb, surrounding sections) and generates the questions that section can answer. These questions become the search index.

We use [keprompt](https://github.com/your/keprompt) to call `cerebras/gpt-oss-120b`:

**Prompt template** (`generate_questions.prompt`):

```
.prompt "name":"QIRA-QI", "version":"1.0", "params":{"model":"cerebras/gpt-oss-120b"}
.system You are a question generation engine for a knowledge retrieval system.

Given a documentation section with its context (breadcrumb showing where it sits
in the document hierarchy), generate all the questions a user might ask that this
section can answer.

Rules:
- Generate questions a real user would actually ask
- Include both beginner questions ("How do I...") and expert questions ("What are the parameters for...")
- Include questions about behavior, edge cases, and relationships to other features
- Each question should be answerable from THIS section's content
- Output one question per line, nothing else
.user Breadcrumb: <<breadcrumb>>

Section: <<title>>

Content:
<<content>>
```

The build script calls this prompt for each section, passing the breadcrumb, title, and content. The LLM returns questions — one per line — which become the index entries.

**Why an LLM?** A heuristic can generate "What does json.dumps do?" from a function signature. But only an LLM understands that a section about `indent` parameter also answers "How do I pretty-print JSON?" and "How do I format JSON with tabs instead of spaces?" These are the questions users actually ask.

### 7. Pre-Format Markdown Entries

Build two entries per section, stored in SQLite:

**`search_entry`** — the body of what `qira_search` returns (heading is added by RA at runtime with match distance):

```markdown
> Python Standard Library > json > json.dumps
- *How do I convert a Python object to a JSON string?*
- *How do I pretty-print JSON in Python?*
- *What parameters does json.dumps accept?*

json.dumps(obj, *, skipkeys=False, ensure_ascii=True, indent=None, separators=None, default=None, sort_keys=False)...
```

**`read_entry`** — what `qira_read` returns verbatim:

```markdown
# python-stdlib:1.1.2 json.dumps
> Python Standard Library > json > json.dumps

`json.dumps(obj, *, skipkeys=False, ensure_ascii=True, ...)`

Serialize `obj` to a JSON formatted string.

### Parameters
...

### Example
...

## Subsections
- python-stdlib:1.1.3 json.loads
```

### 8. Vectorize and Store

- Create a ChromaDB collection with the chosen embedding function
- Add all generated questions with their section ID as metadata
- Write sections to SQLite (`id`, `title`, `search_entry`, `read_entry`)
- Write `corpus.md` with corpus name, description, embedding config, and a worked example

ChromaDB stores the embedding function internally — the QIRA runtime queries with plain text and never needs to know which model was used.

## Running the Build

```bash
# From the QIRA project root
cd examples/python-stdlib

# Build the corpus (processes all modules, calls LLM for question generation)
../../.venv/bin/python3 build_corpus.py \
  --source /tmp/cpython-docs/Doc/library \
  --output ../../test-corpus/python-stdlib \
  --modules json,datetime,pathlib,re,os.path,collections,itertools,argparse,csv,logging

# Or build all modules (takes longer, more API calls)
../../.venv/bin/python3 build_corpus.py \
  --source /tmp/cpython-docs/Doc/library \
  --output ../../test-corpus/python-stdlib
```

## Verifying the Corpus

Test with the QIRA runtime:

```bash
# Search
echo '{"corpus":"python-stdlib","question":"How do I pretty-print JSON?"}' \
  | ../../.venv/bin/python3 ../../src/qira qira_search

# Read
echo '{"section_id":"python-stdlib:1.1.2"}' \
  | ../../.venv/bin/python3 ../../src/qira qira_read
```

## Installing the Corpus

Copy the output directory to your project's `prompts/functions/qira-corpus/`:

```bash
cp -r ../../test-corpus/python-stdlib /path/to/your/project/prompts/functions/qira-corpus/
```

Then regenerate the prompt:

```bash
/path/to/your/project/prompts/functions/qira --initialize
```

The Python stdlib is now available to the LLM via `qira_search(corpus="python-stdlib", ...)`.

## Adapting This Example

To build a corpus from your own documents:

1. **Write an adapter** for your source format (steps 3a-3b). The adapter parses your documents and produces markdown with a section tree.
2. **Everything else is the same** — steps 4-8 are shared infrastructure. Organize, rewrite cross-references, generate questions, pre-format, vectorize, store.

The only thing that changes per source format is the parser. The RST adapter in this example is one reference implementation.
