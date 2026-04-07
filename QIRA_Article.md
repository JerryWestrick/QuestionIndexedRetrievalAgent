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

**This is what should be vectorized.** Not the HR regulations themselves — the *questions* that the HR regulations answer.

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

---

## 6. Practical Economics

A common objection to LLM-generated indexing is cost. The numbers say otherwise.

The Python standard library test corpus — 10 modules, 598 sections — required 598 LLM calls to generate questions. Using Cerebras running an open-source 120B parameter model (`gpt-oss-120b`), the entire question generation step:

- Produced **5,346 questions** across 598 sections
- Cost **less than $0.29** total
- Completed in **under 30 minutes**, single-threaded

That is less than a third of a cent per section. Less than a twentieth of a cent per question.

The cost is dominated by Step 5 of the QI pipeline — question generation — which is the only step that requires an LLM. All other steps (parsing, organizing, cross-reference rewriting, pre-formatting, vectorizing, storing) are deterministic and effectively free.

This cost scales linearly with corpus size, not with query volume. You pay once at index time. Runtime retrieval is just a vector similarity search against ChromaDB and a SQLite lookup — no LLM calls, no API costs, no per-query charges.

For comparison, consider what this buys you: every section in the corpus is now findable by any natural-language question an LLM might ask about it. Not by keyword matching, not by fragment similarity — by precise, contextual questions generated by an LLM that read the section in full context. The index *understands* the content because an LLM built it.

At these economics, the "but LLM indexing is expensive" objection evaporates. The real question is: why would you *not* use intelligence to build your index?

---

## 7. Conclusion: Two Visitors to a Library

Imagine two people walk into a library with the same question.

The first rips pages from every book on the shelf — accounting manuals, programming guides, HR handbooks — tears them into index card-sized pieces, shuffles through the pile looking for one that seems related, and hands a fistful of fragments to an expert, asking for an answer.

The second stops at the card catalog. Looks up the topic. Reads the index. Identifies the relevant sections. Walks to the right shelf, opens the right book to the right chapter, reads it in context, follows the "see also" references, and then — with full understanding — provides an answer.

RAG is the first visitor. QIRA is the second.

The technology to build either system exists today. The question is not what tools we use, but whether we engineer with them — or just hope.
