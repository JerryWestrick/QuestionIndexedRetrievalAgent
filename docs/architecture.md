# QIRA Architecture

## Design Principle

The LLM is the only component that understands language. Every architectural decision exists to make the LLM's job easier.

This means:
- **Index time:** Do the heavy lifting upfront — parse structure, generate questions, build metadata — so the LLM at runtime receives clean, pre-organized information.
- **Runtime interface:** Minimal complexity. Simple inputs (strings), natural outputs (markdown). The LLM should never struggle with the tool itself.
- **Output format:** Markdown, because that's the LLM's native format. Structured enough to convey hierarchy and metadata, natural enough to read without parsing. Every element (headings, blockquotes, lists) carries semantic meaning the LLM already knows.
- **Navigation:** Hierarchical section IDs let the LLM navigate by reasoning, not by learning extra tools.

The test: if the LLM wastes context figuring out how to use QIRA or how to interpret its output, the design has failed.

## System Overview

Two pipelines, shared infrastructure:

```
┌─────────────────────────────────────────────────┐
│                 QIRA SYSTEM                     │
│                                                 │
│  ┌───────────────┐       ┌───────────────────┐  │
│  │  QI Pipeline  │       │   RA Pipeline     │  │
│  │  (offline)    │       │   (runtime)       │  │
│  │               │       │                   │  │
│  │  Ingest ──►   │       │   User ──► LLM    │  │
│  │  Parse  ──►   │       │           │       │  │
│  │  Generate ──► ├──►DB◄─┤   Search ◄┘       │  │
│  │  Vectorize ─► │       │     │             │  │
│  │               │       │   Read ──► LLM    │  │
│  │               │       │           │       │  │
│  │               │       │   Answer ◄┘       │  │
│  └───────────────┘       └───────────────────┘  │
└─────────────────────────────────────────────────┘
```

## QI Pipeline (Offline — Index Time)

### 1. Document Ingestion
- **Input:** Source documents (any format: md, pdf, html, txt, docx...)
- **Output:** Normalized content with metadata
- **Key:** Each document tagged with corpus

### 2. Structure Parser
- **Input:** Normalized document
- **Output:** Section tree — preserving headings, hierarchy, cross-references
- **Key:** Sections are the atomic unit, NOT arbitrary chunks. A section = heading + its content within the document hierarchy.

### 3. Question Generator
- **Input:** Each section WITH its full surrounding context (parent headings, position in doc)
- **Output:** Set of questions this section can answer
- **Engine:** LLM call per section
- **Key:** LLM sees full context, not isolated fragment. Questions are the index entries.

### 4. Question Vectorizer
- **Input:** Generated questions
- **Output:** Vector embeddings stored in vector DB
- **Stored metadata per question:**
  - Source document path
  - Corpus tags
  - Section hierarchy (breadcrumb)
  - Section position + length in source
  - Introductory excerpt (first ~200 chars of section)
  - Back-reference to parent question set

## RA Pipeline (Runtime — Query Time)

### 1. Query Reception
- User asks natural language question
- LLM receives question in conversation context

### 2. Query Formulation
- LLM reformulates user's raw question → precise, well-scoped query
- LLM identifies relevant corpus
- LLM calls tool: `qira_search(corpus="...", question="...")`

### 3. Semantic Search
- Open corpus's ChromaDB collection
- Query with text: `collection.query(query_texts=[question], n_results=N)` — ChromaDB embeds the query internally using the same embedding function QI configured at index time. RA never sees a vector.
- Question-to-question matching (same semantic structure both sides)
- Corpus filtering is implicit — each corpus has its own ChromaDB collection
- Return top-N section IDs

### 4. Result Presentation
- Return structured results to LLM (NOT raw content):
  - Matched questions (what each section answers)
  - Document path + section breadcrumb
  - Introductory excerpt
  - Source location for full read

### 5. Selective Reading
- LLM browses results, decides what to read
- Reads selected sections in **original document context** (not fragments)
- Follows cross-references if needed ("see also Section X")
- May issue follow-up `qira_search()` calls if needed

### 6. Answer Synthesis
- LLM answers user with full coherent context
- Every token in context window was deliberately selected

## Component Stack

| Component | Used by | Role | Candidates |
|-----------|---------|------|------------|
| Vector DB | QI + RA | Store question embeddings + metadata; embed queries at search time | ChromaDB |
| Embedding Model | QI only | Vectorize questions at index time. ChromaDB stores the embedding function — RA never sees vectors. | Per corpus: OpenAI, sentence-transformers, Cohere, etc. |
| LLM | QI + RA | Question generation (QI), query formulation + reading + answering (RA) | Claude, GPT-4, etc. |
| Document Parser | QI only | Extract structure from source formats | Custom per format (markdown→AST, PDF→structured, etc.) |
| Section Store | QI + RA | Pre-formatted sections served verbatim | SQLite |
| Tool Interface | RA only | `qira_search`/`qira_read` exposed to LLM | KePrompt function calling |

## Tool Interface

Two tools. Strings in, markdown out. The `qira_` prefix is required — these operate in applicational context (bookkeeping, HR, etc.) where generic names would be ambiguous.

### `qira_search(corpus, question, n_results=5)` → markdown

LLM provides corpus, question, and optional n_results (default 5). Returns markdown listing matching sections:

```markdown
## -0.12- hr-regulations:3.2.4 Vacation Policies
> HR Regulations > Employee Benefits > Vacation Policies
- *How many vacation days do employees get?*
- *What law governs vacation policy?*

Software House Merida assigns vacation according to...

## -0.45- hr-regulations:3.2.4.2 Employee Allotment
> HR Regulations > Employee Benefits > Vacation Policies > Employee Allotment
- *How are vacation days calculated per employee?*

Each full-time employee receives annual vacation days based on...
```

**Response structure (per hit):**
- `## -{distance}- {id} {title}` — heading assembled by RA at runtime. Distance (lower = better match), section ID (globally unique address used for `qira_read`), and human title. When multiple questions match the same section, the section appears once with the best (lowest) distance.
- `> {breadcrumb}` — path from document root to this section. Gives domain context.
- `- *{question}*` — all questions this section answers. Shows the LLM what the section covers.
- Plain text — excerpt, opening ~200 chars of the section. Enough to judge relevance without reading the full section.

### `qira_read(section_id)` → markdown

LLM provides one string (e.g. `'hr-regulations:3.2.4'`). Returns the section as readable markdown:

```markdown
# hr-regulations:3.2.4 Vacation Policies
> HR Regulations > Employee Benefits > Vacation Policies

Software House Merida assigns vacation according to
Mexican Labor Law #21kk3m. All full-time employees...

## Subsections
- hr-regulations:3.2.4.1 Definitions
- hr-regulations:3.2.4.2 Employee Allotment
- hr-regulations:3.2.4.3 Carryover Rules
```

**Response structure:**
- `# {corpus}:{hierarchy} {title}` — section heading. `h1` (vs `h2` in search) signals this is a full read, not a listing.
- `> {breadcrumb}` — path from root. Orients the LLM in the document tree.
- Body text — full section content in original markdown formatting.
- `## Subsections` — children of this section, listed as `- {corpus}:{hierarchy} {title}`. These are navigation options downward. Omitted if section has no children.

### Navigation

No navigation tools needed. Section IDs are globally unique hierarchical addresses. The LLM reads `hr-regulations:3.2.4` and knows:
- Parent: `qira_read('hr-regulations:3.2')` 
- Sibling: `qira_read('hr-regulations:3.2.5')`
- Child: `qira_read('hr-regulations:3.2.4.1')` (listed in subsections)

### Design Principle

Minimal LLM complexity. No structured objects to construct or parse. Two strings in, markdown out. Almost impossible to make a bad call.

## Key Architectural Decisions

1. **Sections, not chunks.** Atomic unit respects document structure.
2. **Questions are the index.** Not content embeddings.
3. **LLM drives retrieval.** No dumb pipeline making critical decisions.
4. **Corpus scoping.** Corpus boundaries prevent cross-domain noise.
5. **Read-on-demand.** Context window loaded surgically, not stuffed.
6. **Iterative.** LLM can search → read → search again. Not one-shot.
