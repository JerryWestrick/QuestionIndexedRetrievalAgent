# QI/RA Interface Specification

This document defines the complete contract between the QI (Question Indexing) pipeline and the RA (Retrieval Agent) runtime. Any system that produces output conforming to this spec is QI-compliant. Any system that consumes this format is RA-compliant.

## Corpus Directory Structure

QI produces one directory per corpus. RA discovers corpora by scanning for these directories.

```
{corpus}/
  {corpus}.db           # SQLite database (sections only)
  chroma/               # ChromaDB vector index
  corpus.md             # Corpus identity: name, description, worked example
```

`{corpus}` is a lowercase, hyphenated identifier (e.g. `hr-regulations`, `textual-python`). It appears in the directory name, the database filename, and as the prefix in all section IDs throughout the system.

## Section IDs

### Format

`{corpus}:{hierarchy}` — always, everywhere, no exceptions.

- `{corpus}` — the corpus directory name (e.g. `hr-regulations`)
- `{hierarchy}` — dot-separated numeric path reflecting document structure (e.g. `3.2.4`)
- Full ID: `hr-regulations:3.2.4`

### One ID, one format

The full corpus-prefixed ID is used in every context:
- SQLite `sections.id` column
- ChromaDB `metadata.section_id`
- All markdown content (`search_entry`, `read_entry`)
- Cross-references within content
- `qira_read()` calls from the LLM
- `qira_search()` results returned to the LLM

There is no "local" or "unprefixed" form. The ID is always `{corpus}:{hierarchy}`.

### Navigation

The LLM derives navigation from the ID structure. No additional tools or metadata needed:

- Parent: `hr-regulations:3.2.4` → `hr-regulations:3.2`
- Sibling: `hr-regulations:3.2.4` → `hr-regulations:3.2.5`
- Child: listed under `## Subsections` in `read_entry`

## SQLite Schema: `{corpus}.db`

### `sections` table

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PRIMARY KEY | Full corpus-prefixed section ID (e.g. `hr-regulations:3.2.4`). |
| `title` | TEXT | Section title (e.g. `Annual Allotment`). Used by RA to build the search result heading. |
| `search_entry` | TEXT | Pre-formatted markdown body (breadcrumb, questions, excerpt). RA adds the heading (`## -{distance}- {id} {title}`) at runtime. Must conform to the search entry format below. |
| `read_entry` | TEXT | Pre-formatted markdown. Served verbatim by `qira_read`. Must conform to the read entry format below. |

This is the only table. No metadata table — corpus identity lives in `corpus.md`.

## ChromaDB Schema: `chroma/`

Each entry represents one generated question linked to a section.

| Field | Description |
|-------|-------------|
| `document` | The question text (e.g. "How many vacation days does an employee get per year?") |
| `embedding` | Vector embedding of the question |
| `metadata.section_id` | Full corpus-prefixed section ID (e.g. `hr-regulations:3.2.4`). Back-reference to `sections.id` in SQLite. |

### Embedding Ownership

The embedding model is a **QI-only concern**. QI selects an embedding function (e.g. OpenAI `text-embedding-3-small`, sentence-transformers `all-MiniLM-L6-v2`) and creates the ChromaDB collection with it. ChromaDB stores the embedding function internally. At query time, RA calls `collection.query(query_texts=[...])` and ChromaDB embeds the query using the same function — RA never sees a vector, never imports an embedding library, and never needs to know which model was used.

The embedding model choice is recorded in `corpus.md` for documentation and reproducibility, but RA does not read it.

## Markdown Formats — THE CONTRACT

The markdown formats for `search_entry` and `read_entry` are the core of the QI/RA interface. These formats are non-negotiable. They are documented in three places that must match exactly:

1. **QI output** — what the preparation pipeline writes into SQLite
2. **RA output** — what the runtime serves (search_entry body from SQLite + heading added by RA at runtime)
3. **`qira.prompt`** — what the LLM is taught to expect

If any of these three diverge, the system breaks. The formats below are the single source of truth.

### `search_entry` format

The search result the LLM sees is assembled by RA from two parts:
- **Heading** — added by RA at runtime: `## -{distance}- {id} {title}`
- **Body** — served verbatim from SQLite `search_entry` column

#### QI stores in SQLite (`search_entry` column):

```markdown
> {breadcrumb}
- *{question}*
- *{question}*

{excerpt}
```

#### RA assembles and returns to the LLM:

```markdown
## -{distance}- {id} {title}
> {breadcrumb}
- *{question}*
- *{question}*

{excerpt}
```

| Element | Source | Format | Purpose |
|---------|--------|--------|---------|
| Heading | RA (runtime) | `## -{distance}- {id} {title}` — h2 | Distance (lower = better match), section ID (the LLM copies the `{id}` directly into `qira_read` calls), and human title. |
| Breadcrumb | QI (SQLite) | `> {root} > {parent} > ... > {title}` — blockquote, ` > ` separated | Path from document root to this section. Gives the LLM domain context. |
| Questions | QI (SQLite) | `- *{question}*` — bulleted, italicized | All questions this section answers. Shows the LLM what the section covers. |
| Excerpt | QI (SQLite) | Plain text, ~200 characters | Opening content of the section. Enough to judge relevance without a full read. |

The distance is the best (lowest) match from ChromaDB when multiple questions for the same section match. When deduplicating, the section keeps the strongest match distance.

#### Example

```markdown
## -0.12- hr-regulations:3.1.1 Annual Allotment
> HR Regulations > Employee Benefits > Vacation Policies > Annual Allotment
- *How many vacation days does an employee get per year?*
- *What is the minimum vacation allotment under Mexican labor law?*

Per Mexican Federal Labor Law Article 76, employees are entitled to...
```

### `read_entry` format

```markdown
# {id} {title}
> {breadcrumb}

{full content}

## Subsections
- {child_id} {child_title}
- {child_id} {child_title}
```

| Element | Format | Purpose |
|---------|--------|---------|
| Heading | `# {id} {title}` — h1, space-separated | h1 (not h2) signals a full read, not a search listing. `{id}` is the full corpus-prefixed ID. |
| Breadcrumb | `> {root} > {parent} > ... > {title}` — blockquote, ` > ` separated | Same format as search. Orients the LLM in the document tree. |
| Content | Original markdown, preserving formatting | Full section body. Sub-sections below the readable unit depth are inlined as `###` headings within the content. |
| Subsections | `## Subsections` followed by `- {child_id} {child_title}` list | Children at the same readable unit level. Navigation options downward. **Omit entirely if the section has no children.** IDs are full corpus-prefixed. |

#### Example

```markdown
# hr-regulations:3.1 Vacation Policies
> HR Regulations > Employee Benefits > Vacation Policies

Software House Merida assigns vacation according to
Mexican Labor Law #21kk3m. All full-time employees...

### Calculation by Seniority

Years 1-4: statutory minimum plus five days (17-23 days total)...

### Part-Time Employee Proration

Part-time employees receive vacation days prorated based on...

## Subsections
- hr-regulations:3.1.1 Annual Allotment
- hr-regulations:3.1.2 Request and Approval
- hr-regulations:3.1.3 Carryover Rules
```

## `corpus.md`

Each corpus directory includes a `corpus.md` that provides the corpus identity, embedding config, and a worked example. This file is read by `--initialize` to generate `qira.prompt`. It is never loaded directly into the LLM's prompt — `--initialize` extracts what it needs and composes one unified prompt.

### Format

Markdown with four fixed `## ` headings. `--initialize` splits on headings and extracts each section's content (stripped of leading/trailing whitespace).

```markdown
## Name
HR Regulations

## Description
Mexican labor law, employee benefits, company HR policies for Software House Merida.

## Embedding
openai/text-embedding-3-small

## Example
User asks: "As a part-time employee that started on June 1st, how many days vacation do I get this year?"

1. Do I know enough to answer? No — I need vacation rules for part-time employees.
   qira_search(corpus="hr-regulations", question="How many days vacation for part-time employees?")

2. Browse results. Read the most relevant hit.
   qira_read(section_id="hr-regulations:3.1.1")

3. Do I know enough to answer? Not yet — content mentions proration for mid-year starts but references a formula in another section.
   qira_read(section_id="hr-regulations:3.1.2")

4. Do I know enough to answer? Yes. Answer the user.
```

### Sections

| Heading | Content | Used by |
|---------|---------|---------|
| `## Name` | Corpus display name (single line) | `--initialize` → corpus catalog table in `qira.prompt` |
| `## Description` | What this corpus covers (free text) | `--initialize` → corpus catalog table in `qira.prompt` |
| `## Embedding` | `{library}/{model}` (e.g. `openai/text-embedding-3-small`) | Documentation/reproducibility only. RA does not read this — ChromaDB stores the embedding function internally. |
| `## Example` | Realistic user question + QIRA tool calls showing search → browse → read → answer | `--initialize` picks one corpus's example for `$worked_example` in the prompt template |

## Cross-References

All internal cross-references in source documents must be rewritten by QI to full corpus-prefixed IDs before storing. "See section 3.1.2" becomes "see section hr-regulations:3.1.2" in the stored markdown. The LLM can act on these immediately without inferring the corpus.

## Prompt Generation: `qira.prompt`

RA generates `qira.prompt` (via `prompts/functions/qira --initialize`) by scanning all corpus directories. It reads `corpus.md` from each and composes a single prompt that:

- Explains QIRA mechanics once (tool usage, markdown formats, navigation)
- Lists all corpora in a catalog table (name + description, from each `corpus.md`)
- Includes one worked example (from one corpus's `corpus.md`)

One prompt, one voice. Individual corpus files are input to this process, never included raw.

## Compliance Summary

### QI-compliant system must:
1. Produce a corpus directory with the structure above
2. Populate SQLite `sections` table with full corpus-prefixed IDs and titles
3. Format `search_entry` body (no heading) and `read_entry` markdown **exactly** as specified — this is the contract
4. Populate ChromaDB with question embeddings linked to full corpus-prefixed section IDs
5. Use full corpus-prefixed IDs in all markdown content
6. Rewrite all cross-references to full corpus-prefixed IDs
7. Include a `corpus.md` with name, description, embedding config, and worked example

### RA-compliant system must:
1. Discover corpora by scanning for corpus directories
2. Assemble search results: add `## -{distance}- {id} {title}` heading to each `search_entry` body; deduplicate by section ID keeping best distance
3. Serve `read_entry` verbatim — zero transformation
4. Return `## Nothing Found\n` when search yields no results
5. Provide a KePrompt external-function compatible executable named `qira`
6. Generate `qira.prompt` from `corpus.md` files via `qira --initialize` (release tool)
7. Expose `qira_search(corpus, question, n_results=5)` and `qira_read(section_id)`
8. Errors to stderr with non-zero exit per KePrompt protocol
