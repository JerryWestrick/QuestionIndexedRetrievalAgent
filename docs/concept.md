# QIRA Concept

## Problem
RAG is hope-based. It destroys document structure (chunking), embeds decontextualized fragments, and lets cosine similarity — a math op — make the critical retrieval decision before the LLM sees anything. The most intelligent component (LLM) gets the worst input last.

## Core Insight
The LLM understands the question. It knows what it doesn't know. It naturally thinks in questions. So index **questions**, not content. Match question-to-question (like against like) instead of question-to-statement (apples to motorcycles).

## QIRA = Question Indexed Retrieval Agent

**QI (Question Indexing)** — offline/index time:
1. Organize docs by corpus
2. Preserve document structure (headings, hierarchy, cross-refs)
3. LLM reads each section in full context → generates questions that section answers
4. Vectorize those questions + store structured metadata (path, section, position, excerpt)

**RA (Retrieval Agent)** — runtime:
1. User asks question
2. LLM reformulates with precision, specifies corpus
3. Calls `qira_search(corpus="...", question="...")`
4. Semantic search: LLM's question vs pre-generated questions (like vs like)
5. Returns structured results: doc paths, matched questions, excerpts — not chunks
6. LLM browses results, reads selected sections in original context
7. LLM follows cross-references as needed
8. LLM answers with full coherent context

## Why It Works
- Question-to-question = same semantic space, better cosine similarity
- Both sides LLM-refined (index-time generation + runtime reformulation)
- Structure preserved, not destroyed
- Corpus filtering narrows search before it starts
- Context window used surgically — LLM picks what earns its place
