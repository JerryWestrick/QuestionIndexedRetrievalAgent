# QI Pipeline (Question Indexing)

## Purpose

Take source documents, do all the heavy lifting, produce a ready-to-serve corpus directory. The runtime does zero processing — QI does it all upfront.

## Input

- Source documents in any format (markdown, PDF, docx, HTML, etc.)
- Corpus metadata: name, description

## Output

```
{corpus}/
  {corpus}.db           # SQLite: sections table + meta table
  chroma/               # ChromaDB: question vector index
  example_question.md   # worked example for qira.prompt
```

## Pipeline Steps

### 1. Parse (format-specific adapter)
Extract hierarchical structure from source format. Identify headings, sections, sub-sections, cross-references. This is the only step that differs per format:
- Markdown: heading levels (`#`, `##`, `###`)
- PDF: heading detection, TOC extraction
- Docx: heading styles
- HTML: `<h1>`–`<h6>` tags

### 2. Convert to markdown
Transform all content to markdown, preserving the structure identified in step 1. After this step, everything downstream works with markdown regardless of source format. This is the boundary between format-specific and shared infrastructure.

### 3. Organize
- Assign hierarchical IDs (`3`, `3.1`, `3.1.1`, etc.)
- Build breadcrumbs from the section tree (`HR Regulations > Employee Benefits > Vacation Policies`)
- Determine readable units — the leaf depth at which sections are self-contained enough for LLM comprehension. Deeper levels become inline content (`###` headings) within their parent's read_entry, not separate sections.

### 4. Rewrite cross-references
Convert all internal references to full corpus-prefixed IDs. "See section 3.1.2" becomes "see section hr-regulations:3.1.2". Must happen before pre-formatting so the final markdown contains actionable IDs.

### 5. Generate questions (LLM call)
For each readable unit, an LLM reads the section in its full context (parent headings, breadcrumb, surrounding sections) and generates the questions that section can answer. These questions become the search index — the core of QIRA.

### 6. Pre-format markdown
Build two pre-formatted entries per section, stored as-is in SQLite:

**`search_entry`** — body of what `qira_search` returns per hit. Does NOT include the heading — RA adds `## -{distance}- {id} {title}` at runtime with the match distance from ChromaDB.
```markdown
> HR Regulations > Employee Benefits > Vacation Policies > Annual Allotment
- *How many vacation days does an employee get per year?*
- *What is the minimum vacation allotment under Mexican labor law?*

Per Mexican Federal Labor Law Article 76, employees are entitled to...
```

**`read_entry`** — what `qira_read` returns:
```markdown
# hr-regulations:3.1.1 Annual Allotment
> HR Regulations > Employee Benefits > Vacation Policies > Annual Allotment

Per Mexican Federal Labor Law Article 76, employees are entitled to a minimum
of twelve working days of paid vacation after one year of service...

### Calculation by Seniority

Years 1-4: statutory minimum plus five days (17-23 days total)...

### Part-Time Employee Proration

Part-time employees receive vacation days prorated based on...

## Subsections
- hr-regulations:3.1.2 Request and Approval
- hr-regulations:3.1.3 Carryover Rules
```

Sub-sections below the readable unit are inlined as `###` headings. Sibling sections at the same level are listed under `## Subsections`.

### 7. Vectorize
Create a ChromaDB collection with the chosen embedding function (e.g. OpenAI `text-embedding-3-small`, sentence-transformers `all-MiniLM-L6-v2`). The embedding model is a QI engineering choice per corpus — ChromaDB stores the function internally so RA can query with plain text at runtime without knowing or caring which model was used.

Add all generated questions to the collection. Each entry stores:
- Question text + embedding (ChromaDB handles the embedding)
- Section ID (back-reference to SQLite)

### 8. Store
- Write sections to SQLite `sections` table (id, title, search_entry, read_entry)
- Write `corpus.md` with Name, Description, Embedding config, and worked Example (see qi-ra-interface.md for format)

## Production Numbers (Python stdlib corpus)

Test corpus: 10 modules, 598 sections, using Cerebras `gpt-oss-120b`.

| Metric | Value |
|--------|-------|
| Sections | 598 |
| Questions generated | 5,346 |
| Total cost (Step 5) | < $0.29 |
| Wall time (single-threaded) | < 30 minutes |
| Cost per section | < $0.0005 |
| Cost per question | < $0.00006 |

Steps 1-4 and 6-8 are deterministic — effectively zero cost. All spend is in Step 5 (question generation), the only LLM call.

## Adapter Boundary

Steps 1-2 are **format-specific** — each source format needs its own adapter.

Steps 3-8 are **shared infrastructure** — identical regardless of source format. Once content is markdown with structure identified, the rest is the same pipeline.

```
Source ──► [1. Parse  2. Convert] ──► Markdown + Structure
               (adapter)                    │
                                            ▼
                              [3. Organize  4. Rewrite
                               5. Generate  6. Pre-format
                               7. Vectorize 8. Store]
                                   (shared)
                                            │
                                            ▼
                                    Corpus Directory
```
