# QIRA Competition Study

## Question-Indexed Retrieval (Core Idea)

Multiple independent implementations exist:

- **QuIM-RAG** (Saha, Saha, Malik — Jan 2025, arXiv 2501.02702): "Question-to-question Inverted Index Matching." Generates questions from
  document chunks using GPT-3.5-turbo-instruct, embeds them with BAAI/bge-large-en-v1.5, builds a quantized inverted index, and matches user
  queries against pre-generated questions. F1 improved from 0.31 (traditional RAG) to 0.67.
  - https://arxiv.org/abs/2501.02702

- **QuOTE** (Neeser et al. — Feb 2025, arXiv 2502.10976): "Question-Oriented Text Embeddings." Augments chunks with hypothetical questions
  to enrich the representation space. Tested across diverse benchmarks including multi-hop QA.
  - https://arxiv.org/abs/2502.10976

- **Question-Based Retrieval using Atomic Units** (Raina & Gales, Cambridge — May 2024, arXiv 2405.12363): Decomposes chunks into atomic
  statements, then generates synthetic questions on each atom. Shows higher recall than chunk-based retrieval.
  - https://arxiv.org/abs/2405.12363

- **Answerable Question Embeddings** (Aug 2025, arXiv 2508.09755): Replaces standard chunk embeddings with answerable question (AQ)
  representations generated from each chunk using Qwen3-8B. Combines with query decomposition for multi-hop QA.
  - https://arxiv.org/abs/2508.09755

- **HyPE** (Hypothetical Prompt Embeddings): Open source implementation in NirDiamant/RAG_Techniques repository. Precomputes hypothetical
  questions during indexing, stores in FAISS, matches question-to-question at query time. Reports up to 42 percentage point improvement in
  retrieval precision.
  - https://github.com/NirDiamant/RAG_Techniques/blob/main/all_rag_techniques/HyPE_Hypothetical_Prompt_Embeddings.ipynb

- **LlamaIndex `QuestionsAnsweredExtractor`**: Built-in metadata extractor that generates a `questions_this_excerpt_can_answer` field for each
  chunk during indexing. Production-ready, part of their standard pipeline.
  - https://docs.llamaindex.ai/en/stable/module_guides/indexing/metadata_extraction/

- **LangChain Multi-Vector Retriever**: Supports storing multiple vectors per document, including hypothetical questions alongside summaries
  and sub-chunks.
  - https://python.langchain.com/v0.2/docs/how_to/multi_vector/

- **LangChain4j (Java)**: Full implementation of Hypothetical Question Embedding with Vertex AI/Gemini models.
  - https://glaforge.dev/posts/2025/07/06/advanced-rag-hypothetical-question-embedding/

- **GraphRAG Hypothetical Question Retriever**: Part of the GraphRAG ecosystem.
  - https://graphrag.com/reference/graphrag/hypothetical-question-retriever/

### Related but Different: HyDE

- **HyDE** (Gao et al., Dec 2022, arXiv 2212.10496): "Precise Zero-Shot Dense Retrieval without Relevance Labels." Generates a hypothetical
  *answer* to the user's query, then embeds that answer to search for similar real documents. This is the **inverse** of question-indexing:
  HyDE transforms the query side, while QIRA/HyPE transforms the document side. Both aim for "like against like" matching, from opposite
  directions.
  - https://arxiv.org/abs/2212.10496

### Early Practitioner Work

- **Brad Ito, "Don't Jeopardize Your RAG"** (Nov 2023): Early practitioner articulation of the question-generation approach, with two
  open-source tools (`chatbot-confidential`, `parallel-parrot`). Notable quote: "We haven't found any academic papers about this approach"
  (at the time of writing).
  - https://bradito.me/blog/dont-jeopardize-your-rag/

- **Epsilla blog** by Richard Song: "Aligning Question and Document Embedding Spaces with Hypothetical Questions."
  - https://blog.epsilla.com/demystifying-rag-empowered-chat-agents-aligning-question-and-document-embedding-spaces-with-5710c4218464


## LLM-Driven / Agentic Retrieval

Now a major research area with its own survey papers:

- **Agentic RAG Survey** (Jan 2025, arXiv 2501.09136): Comprehensive survey of systems where LLMs make retrieval decisions — query
  reformulation, source selection, result evaluation, iterative refinement.
  - https://arxiv.org/abs/2501.09136

- **FLARE** (Jiang et al., May 2023, arXiv 2305.06983): "Forward-Looking Active REtrieval." The LLM decides *when* to retrieve (based on
  token confidence) and *what* to retrieve (by generating a temporary next sentence as query).
  - https://arxiv.org/abs/2305.06983

- **CRAG** (Yan et al., Jan 2024, arXiv 2401.15884): "Corrective Retrieval Augmented Generation." Adds a retrieval evaluator that assesses
  relevance and triggers different actions (Correct/Incorrect/Ambiguous), including web search fallback.
  - https://arxiv.org/abs/2401.15884

- **Self-RAG**: LLM generates reflection tokens to decide when to retrieve and whether retrieved passages are relevant.

- **PaperQA2** (Future House): Agentic RAG for scientific literature. Iteratively refines queries, performs LLM-based re-ranking and
  contextual summarization. Achieves superhuman performance on scientific literature search.
  - https://github.com/Future-House/paper-qa
  - https://arxiv.org/abs/2312.07559

- **LlamaIndex Agentic Retrieval**: Full framework for building agents that route queries, decompose them into sub-questions, select
  knowledge sources, and iteratively refine answers.
  - https://www.llamaindex.ai/blog/rag-is-dead-long-live-agentic-retrieval

- **DSPy** (Stanford): Framework for programming (not prompting) LLMs. Supports multi-hop retrieval with automatic query reformulation.
  - https://dspy.ai/


## Structure Preservation

- **RAPTOR** (Sarthi et al., Jan 2024, arXiv 2401.18059): "Recursive Abstractive Processing for Tree-Organized Retrieval." Recursively
  clusters and summarizes chunks to build a tree with different levels of abstraction. 20% improvement on QuALITY benchmark with GPT-4.
  - https://arxiv.org/abs/2401.18059
  - https://github.com/parthsarthi03/raptor

- **Microsoft GraphRAG** (Apr 2024, arXiv 2404.16130): Builds a knowledge graph from text, detects hierarchical communities via Leiden
  algorithm, generates community summaries at multiple levels.
  - https://arxiv.org/abs/2404.16130
  - https://microsoft.github.io/graphrag/

- **HiSem-RAG**: Hierarchical Semantic-Driven RAG. Constructs multi-granularity indices based on natural document structures (sections,
  paragraphs), preserving original boundaries.
  - https://www.mdpi.com/2076-3417/16/2/903

- **PT-RAG**: Structure-Fidelity RAG for academic papers. Builds a "PaperTree" index preserving the native outline, performs path-guided
  retrieval.
  - https://arxiv.org/html/2602.13647v1

- **IndexRAG** (Mar 2025, arXiv 2603.16415): Shifts cross-document reasoning from query-time to index-time by identifying bridge entities
  across documents and pre-generating bridging facts.
  - https://arxiv.org/abs/2603.16415


## What Is Genuinely Distinct About QIRA

The individual components are not new — each has been independently developed and published. The name "QIRA" does not appear in any existing
literature. What has *not* been done is combining all three into a unified architecture:

**Not novel (well-established prior art):**
- Generating questions from document sections and embedding them (QuIM-RAG, HyPE, QuOTE, LlamaIndex, LangChain)
- Question-to-question matching at retrieval time
- LLM-driven retrieval with query reformulation and result evaluation (Agentic RAG, FLARE, CRAG, Self-RAG)
- Structure-aware indexing that preserves document hierarchy (RAPTOR, GraphRAG, HiSem-RAG, PT-RAG)

**Distinct in combination:**
- Most question-indexing papers still use standard chunking — QIRA preserves full document structure
- Most agentic retrieval systems use standard embeddings — QIRA uses question-only indexing
- Most structure-preservation systems don't use question-indexed retrieval
- The complete elimination of chunk embeddings in favor of *exclusively* question embeddings, with the LLM as the retrieval decision-maker
- Domain scoping before search
- Cross-reference following as a retrieval primitive
- The LLM specifying a domain to scope its search, then driving retrieval iteratively within that domain

**Assessment:** QIRA's value is as a synthesis — a coherent architecture that combines question-indexing, agentic retrieval, and structure
preservation into a single system. The article's articulation of the *why* (the "hope-based programming" critique, the library analogy) is
stronger than most of the academic papers. If published, it should be positioned as an architectural synthesis, citing QuIM-RAG, HyPE, FLARE,
RAPTOR, and GraphRAG as related work.

---

*Research conducted April 2026*