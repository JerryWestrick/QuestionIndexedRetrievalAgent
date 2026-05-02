# QIRA: Question Indexed Retrieval Agent
### An Engineered Alternative to Hope-Based Retrieval

---

## 1. Introduction

Large Language Models have limited attention. Their context window — the space in which they can reason — is finite. They cannot hold all knowledge at once. When a user asks something beyond what the model currently knows, external knowledge must be *inserted* into that context.

This is the central engineering challenge of knowledge-augmented AI: getting the **right** knowledge into a **scarce** resource.

Getting it wrong doesn't just waste context space — it actively confuses the LLM. The model tries to be helpful with whatever it's given, so irrelevant or misleading fragments produce confident, wrong answers. Getting it right enables expert-level responses grounded in authoritative sources.

Retrieval Augmented Generation (RAG) is the dominant approach to this problem. This paper argues that RAG is fundamentally flawed in its architecture — that it relies on hope at every stage rather than engineering — and presents QIRA (Question Indexed Retrieval Agent) as an alternative built from first principles.

---

## 2. RAG: A Critical Analysis

The Retrieval Augmented Generation pipeline is widely adopted, but a step-by-step examination reveals that each stage relies on unverified assumptions rather than engineering guarantees.

### Step 1: Document Gathering

Gather structured documents that you *hope* contain information relevant to future user questions. No verification that coverage exists — you're guessing at sources before any question is asked. You throw Internal Accounting Structure in with Python Programming Language and HR Vacation Policies... and just in case, everything else you can find. You're not curating knowledge — you're hoarding it, because you have no mechanism to know what's relevant until it's too late.

### Step 2: Chunking

Break those structured documents into arbitrary fixed-size pieces — index cards — *hoping* each card makes sense ripped from its surrounding context. A paragraph separated from its heading, its preceding setup, its following conclusion. The document was structured for a reason; chunking destroys that structure. And in doing so, destroys the context that the vector database in the next step needs to work.

### Step 3: Embedding

Build a semantic database of those index cards, *hoping* each decontextualized fragment retains enough meaning for its embedding to be useful. But an embedding of an orphaned fragment is an embedding stripped of the very context you are trying to index.

### Step 4: Retrieval

At runtime — before the LLM sees anything — a cosine similarity function makes the most critical decision in the pipeline: what information the LLM gets to work with. A math operation is doing a reasoning job, matching a raw, potentially vague user question against fragment embeddings. Apples against motorcycles, animals, and the kitchen sink.

### Step 5: Context Stuffing

Shove the selected index cards into the LLM's limited context window alongside the user's question. The LLM must now try to synthesize a coherent answer from fragments that were never designed to be read together — wasting scarce context space and actively confusing the model.

### The Fundamental Flaw

The least intelligent components make the most critical decisions. The only component that actually *understands* language — the LLM — is the last to see anything, and receives the worst possible input.

This is not engineering. This is hope-based programming.

---

## 3. Inverting the Architecture

Start from first principles. Strip away all assumptions about how retrieval "should" work and ask: what is the actual situation?

**The user asked the LLM something it does not have in its context. The LLM knows it doesn't know.**

This is the critical observation that RAG ignores entirely. The LLM is not a passive consumer waiting to be fed — it *understands* the question. It knows what domain it's in. It knows what kind of information would answer it. It knows what it's missing.

So let it ask.

When the LLM needs information, it naturally formulates what it needs to know. It doesn't think in document fragments — it thinks in questions. To answer a user's question about vacation days, the LLM knows it needs to know: "What are the HR regulations about unused vacation days?" This is natural for the LLM. This is what it needs to know to answer the user.

**From first principles:** the goal is to help the LLM find *answers* to its *questions*. So vectorize the questions — **not the answers.**

RAG vectorizes document content and tries to match questions against statements — a context switch between two different forms of language. QIRA vectorizes questions, because that is what the LLM naturally produces; and the purpose of QIRA is to help the LLM with its knowledge context. The LLM asks a question. The index contains questions. No context switch. Like against like.

The LLM already has everything it needs to drive retrieval intelligently:

- It understands the user's intent, even when the question is vague or poorly worded
- It can reformulate the question with proper syntax and precision
- It can identify the domain and topic
- It can evaluate results and decide if it needs more information
- It can follow references and read further

RAG ignores this intelligence. QIRA is built to use LLM intelligence, achieving better informational context loading.

---

## 4. QIRA: Question Indexed Retrieval Agent

QIRA re-engineers retrieval in two phases — encoded in its name:

### QI — Question Indexing

Documents are processed through a pipeline — but unlike RAG, the goal is to preserve structure, not destroy it.

1. **Domain organization.** Documents are organized by topic and domain (programming, accounting, HR) — not thrown into a single pile.

2. **Structure preservation.** Document structure is preserved: headings, hierarchy, sections, cross-references. The document remains navigable.

3. **Question generation.** An LLM reads each section *in its full context* and generates the questions that section can answer. This is the key innovation — the index is made of **questions**, not fragments.

4. **Question vectorization.** Those generated questions are vectorized and stored alongside structured metadata: document path, section hierarchy, source file, position, length, and an introductory excerpt.

### RA — Retrieval Agent

1. The user asks a question.

2. The LLM understands the question. It knows the answer is not in its context.

3. The LLM calls `qira(topic=[...], question="...")` — reformulating the user's question with precision and clarity. The domain is specified, narrowing the search space.

4. QIRA performs semantic search: the LLM's well-formed question against pre-generated well-formed questions. Question against question. Like against like.

5. QIRA returns structured results — not chunks, but a map: document paths, the questions each section answers, source locations, introductory excerpts.

6. The LLM browses the results, selects what to read, and reads those sections in their original structured context.

7. If a section references another ("for color options, see Specifying Colors"), the LLM follows it — just as a human would.

8. The LLM answers the user with full, coherent context.

The LLM drives every decision. Retrieval is not a gamble — it is a directed, intelligent process.

---

## 5. Why It Works

The same underlying technologies — embeddings, vector search, LLMs — are used in both RAG and QIRA. The difference is not the tools. The difference is where intelligence is applied.

**Question-to-question matching eliminates the context switch.** RAG matches a question against a statement. These are structurally different forms of language — a question asks, a statement declares. Their embeddings occupy different regions of semantic space. QIRA matches a question against a question. Both sides have the same linguistic structure, the same intent framing. Cosine similarity was designed for this — comparing like against like.

**Both sides are LLM-refined.** At index time, an LLM generates well-formed questions from fully contextualized document sections. At run time, the LLM reformulates the user's raw question into a precise, well-scoped query. The vector search operates on clean, intelligent inputs at both ends — not a vague user question against an orphaned fragment.

**Document structure is preserved, not destroyed.** The LLM reads sections in their original context — with headings, preceding material, and cross-references intact. It receives coherent information, not confetti.

**Topic filtering narrows the search space.** Domain boundaries mean "exceptions" in a Python context never competes with "exceptions" in an accounting context. The search is scoped before it begins.

**Context window is used surgically.** Instead of stuffing arbitrary chunks into scarce context space, the LLM selects exactly what it needs. Every token in the context window earns its place.

**The result:** better retrieval, better context, better answers. Not because of better technology — because the same technology is applied correctly.

The architectural moves above don't appear in isolation. Variants of LLM-driven query reformulation, structured/hierarchical retrieval, agent-driven retrieval loops, and richer index targets exist in the literature — HyDE, ReAct, RAPTOR, GraphRAG, Self-RAG, and others. **Appendix C** surveys those approaches and locates QIRA within the landscape. The contribution claimed here is the specific composition: questions-as-index-unit, structured-document preservation, and agent-driven traversal — not any single ingredient.

---

## 6. A Worked Example

Consider a concrete session against the `eu-ai-act` corpus — Regulation (EU) 2024/1689, the EU Artificial Intelligence Act: 180 recitals, 113 articles across 13 chapters, 13 annexes.

**Question:** *"What are the liabilities of AI software providers?"*

**System prompt:** a single `.include prompts/functions/qira.prompt` — a shared instruction file that tells the LLM how to use `qira_search` and `qira_read` and how to cite section IDs. Nothing EU-AI-Act-specific. Same prompt, same corpus, same tool signatures across both runs. **The only variable is the LLM.**

### Run 1 — `openai/gpt-4o-mini`

One search, then tree navigation from the chapters that looked relevant:

```
qira_search("What are the liabilities of AI software providers under the EU AI Act?")
qira_read("eu-ai-act:4")     # Chapter III — High-Risk AI Systems
qira_read("eu-ai-act:5")     # Chapter IV — Transparency Obligations
qira_read("eu-ai-act:4.2")   # Section 2 — Requirements
qira_read("eu-ai-act:4.3")   # Section 3 — Provider obligations
qira_read("eu-ai-act:5.1")   # Transparency requirements
```

Produces a coherent answer organised by chapter, citing Articles 9–17, 20, 21, 27, and 50. Never reaches the Penalties chapter.

**Cost:** $0.0013 · 6,100 input tokens (4.8% of 128K) · 611 output · 20 s wall.

### Run 2 — `cerebras/gpt-oss-120b`

Five searches with progressive reformulation, interleaved with four targeted reads:

```
qira_search("liability of AI software providers", n=5)
qira_search("liability of providers", n=10)
qira_search("liability providers", n=10)
qira_search("liability of AI providers", n=10)
qira_read("eu-ai-act:4.3.1")             # Article 16 — Obligations of providers
qira_search("liable for damage", n=10)   # ← reformulation pivot
qira_read("eu-ai-act:1.79")              # Recital 79 — legal definition of "provider"
qira_search("administrative fines providers", n=10)  # ← reformulation pivot
qira_read("eu-ai-act:7.4")               # Article 60 — real-world testing liability
qira_read("eu-ai-act:13.1")              # Article 99 — Penalties
```

Produces a substantively different answer: the three fine tiers of **Article 99** (€35M / 7% of turnover for prohibited practices, €15M / 3% for other obligations, €7.5M / 1% for false information); **Article 60§9** liability during real-world testing outside sandboxes; **Recital 79** as the legal definition of "provider". These are the actual load-bearing citations for a liability question.

**Cost:** $0.0178 · 47,826 input tokens (36.5% of 131K) · 1,413 output · 28 s wall.

### What changed

Nothing in the infrastructure. Same corpus, same retrieval protocol, same tool signatures, same system prompt. The smarter model chose to:

1. **Search more times** — 5 searches vs. 1.
2. **Adopt the corpus's own terminology from the question index.** The word *liability* never appears in Article 99 — it is titled *Penalties*. A single-shot search on *"liability of providers"* returns weak top hits (Recital 85 on cooperation, Article 57 on sandboxes). But every hit also carries its list of indexed questions, and those lists included phrasings like *"Who is liable for any damage caused during the testing of high‑risk AI systems?"* (attached to Article 60) and *"Under what conditions are administrative fines waived for providers…?"* (attached to Article 57). The model read those questions, learned that this corpus speaks of liability through the words *damage* and *administrative fines*, and reformulated — *"liable for damage"* surfaced Article 60§9, *"administrative fines providers"* eventually surfaced Article 99. The reformulation was not blind retrying; it was vocabulary acquisition from the index itself.
3. **Read specific articles and recitals**, not entire chapters.

No part of the QIRA design anticipated this. Watching the model adjust its own framing — querying, reading the questions attached to near-miss results, lifting their vocabulary, requerying with the corpus's own words — surfaces a property worth naming: **the question index doubles as a domain-vocabulary map.** Every search result, hit or near-miss, exposes the LLM-generated questions for those sections in the corpus's own language. A model reading search results carefully is reading the book's subject index, not just a list of matches.

RAG structurally cannot offer this. RAG returns document *fragments* — noisy, decontextualised text the LLM has to parse as evidence. QIRA returns explicit statements of what each section is about, phrased as the questions it answers. The difference is the difference between a table of contents and a pile of shredded pages.

Retrieval quality scales with the intelligence of the agent driving it. No re-indexing, no re-tuning, no top-k-per-corpus parameter to sweep. Put a smarter model in front of QIRA and retrieval gets smarter, for free. And the runtime cost scales with what the model decides to do — not with corpus size, query volume, or a vector-DB subscription. The "expensive" run above costs under two cents.

### A coincidence worth flagging

The questions in the `eu-ai-act` index were generated by `gpt-oss-120b` — the same model that produced the better retrieval result in Run 2. One can postulate several theories for why a model might search more effectively against an index it wrote itself — shared vocabulary, shared domain decomposition, shared sense of what a meaningful question looks like — but none have been tested here. One data point is not an effect. Flagged as an open question, not claimed as a finding.

### On delivery

Both runs above were executed by [**keprompt**](https://github.com/jeremywestrick/keprompt), a prompt-as-code runtime that pairs naturally with QIRA. A `.prompt` file is a small declarative script: parameters, system instructions, tool registrations, user input, and an `.exec` directive. keprompt handles the multi-turn tool-use loop, routes calls to the model of your choice, and records every token, dollar, and tool invocation to a local SQLite chat log. The traces above were reconstructed by a single `SELECT` against that log.

The entire QIRA retrieval protocol — corpus catalog, tool usage instructions, worked example, response-format documentation — lives in one shared include:

```
.include prompts/functions/qira.prompt
```

Drop that line into any `.prompt` and the LLM gains corpus-grounded answers, with cost and token accounting, multi-turn orchestration, and model-swap via a single CLI flag:

```bash
keprompt new chat test --set question "what are the liabilities of AI software providers?"
keprompt new chat test --set question "..." --set model "cerebras/gpt-oss-120b"
```

The two runs in this section differ by exactly that second flag. Everything else — the protocol, the corpus, the infrastructure — is identical.

**QIRA defines the retrieval architecture. keprompt makes it a one-line include.**

---

## 7. Practical Economics

A common objection to LLM-generated indexing is cost. The numbers say otherwise.

The Python standard library test corpus — 10 modules, 598 sections — required 598 LLM calls to generate questions. Using Cerebras running an open-source 120B parameter model (`gpt-oss-120b`), the entire question generation step:

- Produced **5,346 questions** across 598 sections
- Cost **less than $0.29** total
- Completed in **under 30 minutes**, single-threaded

That is more than 20 sections per penny. More than 180 questions per penny.

The cost is dominated by Step 5 of the QI pipeline — question generation — which is the only step that requires an LLM. All other steps (parsing, organizing, cross-reference rewriting, pre-formatting, vectorizing, storing) are deterministic and effectively free.

This cost scales linearly with corpus size, not with query volume. You pay once at index time. Runtime retrieval is just a local vector similarity search and a structured lookup for section content — no LLM calls, no API costs, no per-query charges.

For comparison, consider what this buys you: every section in the corpus is now findable by any natural-language question an LLM might ask about it. Not by keyword matching, not by fragment similarity — by precise, contextual questions generated by an LLM that read the section in full context. The index *understands* the content because an LLM built it.

At these economics, the "but LLM indexing is expensive" objection evaporates. The real question is: why would you *not* use intelligence to build your index?

---

## 8. Conclusion: Two Visitors to a Library

Imagine two people walk into a library with the same question.

The first rips pages from every book on the shelf — accounting manuals, programming guides, HR handbooks — tears them into index card-sized pieces, shuffles through the pile looking for one that seems related, and hands a fistful of fragments to an expert, asking for an answer.

The second stops at the card catalog. Looks up the topic. Reads the index. Identifies the relevant sections. Walks to the right shelf, opens the right book to the right chapter, reads it in context, follows the "see also" references, and then — with full understanding — provides an answer.

RAG is the first visitor. QIRA is the second.

The technology to build either system exists today. The question is not what tools we use, but whether we engineer with them — or just hope.

---

## Appendix A. Reproduce the §6 Runs

Everything reported in §6 — the tool calls, the costs, the token counts, the answers — is reproducible in ten minutes on a fresh machine. This appendix is the exact sequence.

### Requirements

- Python 3.10+
- An OpenAI API key (for Run 1, `openai/gpt-4o-mini`)
- A Cerebras API key (for Run 2, `cerebras/gpt-oss-120b`)

### Install

```bash
mkdir qira-demo && cd qira-demo
python3 -m venv .venv
source .venv/bin/activate
pip install keprompt model2vec faiss-cpu
```

Pinned versions used for the §6 runs: `keprompt 2.14.0`, `model2vec 0.8.1`, `faiss-cpu 1.13.2`.

### Initialize the keprompt project

```bash
keprompt init
```

This creates `prompts/` and `prompts/functions/` in the current directory. Without this step, every subsequent `keprompt` invocation silently fails with *"Model not defined"*.

### Download and extract the EU AI Act corpus

```bash
cd prompts/functions
curl -L -O https://github.com/JerryWestrick/QuestionIndexedRetrievalAgent/raw/main/corpus/eu-ai-act.zip
unzip eu-ai-act.zip
cd ../..
```

The zip contains the `qira` runtime (dropped into `prompts/functions/qira`) and the corpus data (`prompts/functions/qira-corpus/eu-ai-act/` — three files: `eu-ai-act.db`, `eu-ai-act.faiss`, `corpus.md`).

### Generate the QIRA prompt include

```bash
./prompts/functions/qira --initialize
```

This scans `prompts/functions/qira-corpus/`, reads each corpus's `corpus.md`, and writes `prompts/functions/qira.prompt` — the shared instruction file that tells any LLM how to use `qira_search` and `qira_read`.

### Write the test prompt

Create `prompts/test.prompt`:

```
.prompt "name":"test", "version":"1.0", "params":{"model":"openai/gpt-4o-mini", "question":""}
.functions qira.*
.system You are a helpful assistant. Use qira_search and qira_read to ground answers in the available corpora. Cite section IDs.
.include prompts/functions/qira.prompt
.user <<question>>
.exec
```

Six lines. Every line is load-bearing; see Appendix B.

### Set your API keys

```bash
export OPENAI_API_KEY="sk-..."
export CEREBRAS_API_KEY="csk-..."
```

### Run 1 — `openai/gpt-4o-mini`

```bash
keprompt new chat test --set question "what are the liabilities of AI software providers?"
```

Expected: one `qira_search`, a handful of `qira_read` calls on Chapters III and IV, an answer organised by chapter citing Articles 9–17, 20, 21, 27, and 50. Cost ≈ **$0.0013**, wall time ≈ **20 s**, input tokens ≈ **6,100**. Compare to §6 Run 1.

### Run 2 — `cerebras/gpt-oss-120b`

```bash
keprompt new chat test \
  --set question "what are the liabilities of AI software providers?" \
  --set model "cerebras/gpt-oss-120b"
```

Expected: five `qira_search` calls with progressive reformulation (*"liability of providers"* → *"liable for damage"* → *"administrative fines providers"*), four targeted `qira_read` calls including Article 99 (Penalties) and Article 60 (real-world testing liability). Cost ≈ **$0.018**, wall time ≈ **28 s**, input tokens ≈ **48,000**. Compare to §6 Run 2.

### Inspect the internal tool-call trace

Every chat keprompt runs is logged to `prompts/chats.db`. To see the full tool-call sequence for a given run, use:

```bash
keprompt show chat <chat_id> --pretty
```

The `chat_id` is printed at the end of each run (e.g. `Chat e3473544:1 ...`).

---

## Appendix B. Anatomy of a QIRA Prompt

The six-line `test.prompt` from Appendix A is the minimum viable QIRA-grounded prompt. Each directive does one job.

```
.prompt "name":"test", "version":"1.0", "params":{"model":"openai/gpt-4o-mini", "question":""}
.functions qira.*
.system You are a helpful assistant. Use qira_search and qira_read to ground answers in the available corpora. Cite section IDs.
.include prompts/functions/qira.prompt
.user <<question>>
.exec
```

| Line | Directive | What it does |
|---|---|---|
| 1 | `.prompt` | Declares the prompt's name, version, and typed parameters. `model` and `question` are both overridable at runtime with `--set`. The `model` value here is the default; any valid keprompt model string works (`openai/...`, `anthropic/...`, `cerebras/...`, etc.). |
| 2 | `.functions qira.*` | Registers every tool exported by the `qira` external function — currently `qira_search` and `qira_read`. keprompt discovers them by running `./prompts/functions/qira --list-functions`. |
| 3 | `.system` | System-level instructions to the LLM. Keep this short: the heavy lifting is done by the include on the next line. |
| 4 | `.include prompts/functions/qira.prompt` | Pastes the contents of `qira.prompt` in place. That file is generated by `qira --initialize` and contains the corpus catalog, the tool-use protocol, the worked example, and the response-format documentation. **This one line is QIRA's entire integration with keprompt.** |
| 5 | `.user <<question>>` | Sends the user turn. `<<question>>` is substituted from the `question` parameter. |
| 6 | `.exec` | Tells keprompt to run the multi-turn tool-use loop until the LLM produces a final answer. |

### Swapping the model

The `model` parameter is declared in `.prompt` and overridden at the command line:

```bash
keprompt new chat test --set question "..." --set model "anthropic/claude-sonnet-4-6"
```

No edits to the prompt, no rebuild of the corpus. Retrieval and answer quality will vary with the model — see §6 for the gpt-4o-mini vs. gpt-oss-120b comparison — but the infrastructure is identical.

### Swapping the corpus

The corpus isn't named in the prompt. The LLM picks a corpus at tool-call time based on the catalog in the included `qira.prompt`. To add a second corpus:

```bash
cd prompts/functions
curl -L -O https://.../python-stdlib.zip  # or any other QIRA corpus zip
unzip python-stdlib.zip
cd ../..
./prompts/functions/qira --initialize
```

The re-generated `qira.prompt` now lists both corpora. Ask a Python question and the LLM routes to `python-stdlib`; ask a regulatory question and it routes to `eu-ai-act`. No prompt changes.

### Writing your own prompt from scratch

Any `.prompt` that wants corpus-grounded answers needs exactly two things:

```
.functions qira.*
.include prompts/functions/qira.prompt
```

Everything else — system instructions, user templates, output formatting, multi-turn structure — is yours to design. QIRA stays a one-line dependency.

---

## Appendix C. Prior Art and Adjacent Work

QIRA composes architectural ideas that appear individually elsewhere in the retrieval literature. This appendix surveys those adjacent approaches, organized by where each intervenes in the underlying problem — *the LLM is missing information from its context* — and locates QIRA within the landscape.

### Query-side — improve the LLM's question before retrieval

| Approach | What it does | What it addresses | What it doesn't |
|---|---|---|---|
| **HyDE** (Hypothetical Document Embeddings) | LLM generates a fake answer document; embed *that*; search against real document embeddings | The question-vs-statement embedding mismatch — by faking a statement, both sides of the cosine match are statements | Still searches over chunked text; a wrong hallucinated frame steers retrieval into the wrong neighborhood |
| **Multi-query / RAG-Fusion** | LLM generates N rephrased queries, runs all, fuses results | Brittleness of a single embedding match | Multiplies query cost; underlying chunked-content problem unchanged |
| **Step-back prompting** | LLM asks a more abstract question first, then narrows | Vague-user-query failure mode | Doesn't change what gets indexed |

### Index-side — make the retrieval target richer

| Approach | What it does | What it addresses | What it doesn't |
|---|---|---|---|
| **Doc-summary indexes** | Store per-section LLM summaries alongside chunks; search the summaries | The decontextualized-fragment problem | Still chunks under the hood; quality bound by summarizer |
| **Parent-document retrieval** | Embed small chunks but return their larger parent containers | Context-loss from chunk-only retrieval | Still uses raw chunks as the search unit |
| **Hierarchical retrieval** | Multi-level structure (chapter → section → paragraph); retrieve at the right level | Granularity mismatch | Usually still embeds raw text, not LLM-generated content |
| **RAPTOR** | Recursive cluster + LLM-summarize, building a tree of summaries from leaves up | Coarse-to-fine retrieval over abstractions; long-document QA | Summarized statements (not questions); cluster-then-summarize loses author-intended structure; no agent-driven navigation |
| **GraphRAG / KG-augmented** | Extract entities and relations into a graph; traverse for context | Cross-document relationships flat RAG misses | Heavy index-build, brittle entity extraction; no help when the relevant edge is missing from the graph |

### Agent-driven — let the LLM control retrieval iteratively

| Approach | What it does | What it addresses | What it doesn't |
|---|---|---|---|
| **ReAct** | LLM interleaves reasoning with tool calls including search; retries based on what comes back | Single-shot retrieval failure | The retrieval target itself is unchanged — usually still chunks |
| **Self-RAG / Corrective RAG** | LLM critiques each retrieved chunk, decides if it's useful, re-retrieves if not | Quality filtering of retrieved chunks | Inherits chunked-content brittleness; adds latency |
| **FLARE** | LLM predicts what it would say next, uses that prediction as the query, retrieves to verify | Look-ahead retrieval — fetching what is about to be needed | Same chunked target |

### Long-context as alternative

| Approach | What it does | What it addresses | What it doesn't |
|---|---|---|---|
| **Stuff-it-all-in** (Gemini 1.5, Claude 1M-context, etc.) | Skip retrieval entirely; load full corpus into context | Eliminates the retrieval-segment selection problem | Cost scales linearly with corpus size per query; attention quality degrades with context length; corpus must fit in window |

### Where QIRA sits

QIRA composes three of these moves with one new attribute:

1. **Index-side, with a new attribute.** Like hierarchical retrieval and RAPTOR, QIRA preserves multi-level document structure and stores LLM-generated content alongside the source. The new attribute: the indexed unit is the **questions** each section answers — not summaries, not hypothetical documents, not entities. This is the inversion §3 argues for: the LLM searches in question-space because that is what the LLM internally formulates when it needs information.

2. **Query-side, observed not designed.** The LLM reformulates queries before re-running search (similar in spirit to multi-query). The behavior reported in §6 — vocabulary acquisition from indexed questions — is an emergent property of the question-as-index choice, not a query-side technique engineered for. It functions as an in-band feedback loop without an explicit reformulation step.

3. **Agent-driven, over structure rather than chunks.** Like ReAct, the LLM drives multi-step retrieval. Distinct from chunk-based agents: the retrieval target is structured corpus pointers (section IDs, breadcrumbs, cross-references), so the agent navigates hierarchically and follows cross-references rather than re-querying for new fragments.

What QIRA does **not** combine: cross-document graph relationships (GraphRAG territory) or query-time hypothetical document generation (HyDE territory). These are compatible additions, not competing alternatives.

The contribution is the composition, not any single ingredient. A reader steeped in retrieval literature will recognize each part; the architectural claim is that *questions-as-index-unit + structured-document preservation + agent-driven traversal* is a coherent and engineerable system whose cost economics (§7) make it practical at index build time.

