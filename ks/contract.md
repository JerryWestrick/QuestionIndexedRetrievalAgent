# QI/RA Storage Contract

**Authoritative spec:** `docs/qi-ra-interface.md`. This file condenses it for quick recall.

**Rule:** QI producers write this shape; RA consumers read it. Any divergence between QI output, RA input, and `qira.prompt` documentation **breaks the system**.

## Corpus directory

```
{corpus}/
  {corpus}.db       # SQLite — sections only
  chroma/           # ChromaDB — question vector index
  corpus.md         # Corpus identity (name, description, embedding, example)
```

`{corpus}` is lowercase, hyphenated (e.g. `python-stdlib`, `eu-ai-act`). The directory name, the DB filename, and the section ID prefix must all agree.

## Section ID

Format: `{corpus}:{hierarchy}` — always, everywhere, no exceptions.

- `{hierarchy}` is dot-separated numeric: `3`, `3.2`, `3.2.4`
- Full ID example: `eu-ai-act:4.2.1`
- The corpus prefix appears in every ID in every context (SQLite keys, ChromaDB metadata, markdown content, cross-refs, `qira_read` args). There is **no** "local" or "unprefixed" form.

Navigation is derived from the ID itself — no extra metadata:
- Parent: strip trailing `.N`
- Sibling: change trailing `.N`
- Child: listed under `## Subsections` in the section's `read_entry`

## SQLite schema: `{corpus}.db`

One table: `sections`. No metadata table (corpus identity lives in `corpus.md`).

| Column | Type | Description |
|---|---|---|
| `id` | TEXT PRIMARY KEY | Full corpus-prefixed ID (e.g. `eu-ai-act:4.2.1`) |
| `title` | TEXT NOT NULL | Section title. RA uses this to build the search result heading. |
| `search_entry` | TEXT NOT NULL | Pre-formatted markdown **body** for search hits. RA adds the h2 heading at runtime. |
| `read_entry` | TEXT NOT NULL | Pre-formatted markdown served **verbatim** by `qira_read`. |

## ChromaDB schema: `chroma/`

Collection name: `questions`. One entry per generated question (N per section).

| Field | Content |
|---|---|
| `document` | The question text |
| `embedding` | Vector of the question (ChromaDB handles embedding internally) |
| `metadata.section_id` | Full corpus-prefixed section ID (back-ref to `sections.id`) |
| `ids` | Unique per-question doc ID (builder convention: `q0`, `q1`, ...) |

**Embedding ownership:** The embedding function is a **QI-only concern**. QI picks it, creates the collection with it, ChromaDB stores it. RA queries with `query_texts=[...]` and never imports an embedding library directly — *except* when the collection was created with a non-default embedding function, in which case RA must instantiate the same function to open the collection. See `ks/runtime.md` and `ks/gotchas.md`.

## Markdown formats — THE CONTRACT

Non-negotiable. Must match exactly across QI output, RA output, and `qira.prompt` documentation.

### `search_entry`

**Stored in SQLite** (body only — no heading):

```
> {breadcrumb}
- *{question}*
- *{question}*

{excerpt}
```

**Assembled by RA at runtime** (adds h2 heading with distance):

```
## -{distance}- {id} {title}
> {breadcrumb}
- *{question}*
- *{question}*

{excerpt}
```

| Element | Source | Format |
|---|---|---|
| Heading | RA runtime | `## -{distance:.2f}- {id} {title}` — h2 |
| Breadcrumb | QI/SQLite | `> root > parent > ... > title` — blockquote, ` > ` separated |
| Questions | QI/SQLite | `- *{question}*` — bulleted, italicized |
| Excerpt | QI/SQLite | Plain text, ~200 chars of opening content |

Deduplication: when multiple questions in the same section match a query, the section appears **once**, with the best (lowest) distance.

### `read_entry`

Stored verbatim in SQLite. RA does **zero transformation**.

```
# {id} {title}
> {breadcrumb}

{full content}

## Subsections
- {child_id} {child_title}
- {child_id} {child_title}
```

| Element | Format |
|---|---|
| Heading | `# {id} {title}` — h1. h1 (not h2) signals a full read, not a search listing. |
| Breadcrumb | `> root > parent > ... > title` — same format as search |
| Content | Original markdown, preserving formatting. Sub-sections below the readable unit depth are inlined as `###` headings. |
| Subsections | `## Subsections` + list. **Omit entirely if the section has no children.** IDs are full corpus-prefixed. |

## `corpus.md`

Markdown with four fixed `## ` headings. Parsed by `runtime/qira --initialize` (see `parse_corpus_md` at `runtime/qira:312`).

```
## Name
Human-readable display name.

## Description
What this corpus covers. Goes into the qira.prompt catalog table.

## Embedding
{library}/{model}   e.g. sentence-transformers/all-MiniLM-L6-v2 (PyTorch)
                    or  openai/text-embedding-3-small

## Example
Realistic user question + numbered QIRA tool calls demonstrating search → read → answer.
```

Sections are parsed in order; whitespace stripped. `--initialize` pulls `Name` + `Description` into the corpus catalog table, and picks the first corpus's `Example` as the `$worked_example` in `qira.prompt`.

## Cross-references in content

**All** internal cross-references in source documents must be rewritten by QI to full corpus-prefixed IDs **before** storing. The LLM must be able to act on any reference immediately without inferring the corpus.

- python-stdlib: `:func:` `:class:` `:mod:` role lookups → IDs
- eu-ai-act: plain-text regex for `Article N(M)`, `Annex III`, `Chapter IV`, `Recital (N)` → `{orig} (see eu-ai-act:{id})`

## Compliance checklists

**QI-compliant builder must:**
1. Produce the corpus directory with the structure above
2. Populate `sections` with full corpus-prefixed IDs + titles
3. Format `search_entry` body (no heading) and `read_entry` exactly as specified
4. Populate ChromaDB with question embeddings linked to full corpus-prefixed section IDs
5. Rewrite all cross-references to full corpus-prefixed IDs
6. Write `corpus.md` with the four required headings

**RA-compliant runtime must:**
1. Discover corpora by scanning for corpus directories
2. Assemble search results: add `## -{distance}- {id} {title}` heading, dedupe by section ID, keep best distance
3. Serve `read_entry` verbatim — zero transformation
4. Return `## Nothing Found\n` on empty search
5. Be a KePrompt external-function executable named `qira`
6. Errors to stderr with non-zero exit per KePrompt protocol
