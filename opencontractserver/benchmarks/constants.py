"""Constants for benchmark configuration."""

# HuggingFace dataset URLs for Legal RAG Bench
LEGAL_RAG_BENCH_DATASET = "isaacus/legal-rag-bench"
LEGAL_RAG_BENCH_CORPUS_URL = (
    "https://datasets-server.huggingface.co/rows"
    "?dataset=isaacus/legal-rag-bench&config=corpus&split=test"
)
LEGAL_RAG_BENCH_QA_URL = (
    "https://datasets-server.huggingface.co/rows"
    "?dataset=isaacus/legal-rag-bench&config=qa&split=test"
)

# HuggingFace rows API pagination
HF_ROWS_API_MAX_LIMIT = 100

# Benchmark defaults
DEFAULT_BENCHMARK_NAME = "Legal RAG Bench"
DEFAULT_TOP_K = 5

# RAG prompt for answer generation (matches Legal RAG Bench format)
RAG_PROMPT = """You are a legal research assistant specializing in Victorian criminal law.
Answer the following question using ONLY the provided context passages.
If the context does not contain enough information to answer, say so.

Context:
{context}

Question: {question}

Answer:"""

# Judge prompt for evaluating answer correctness
JUDGE_PROMPT = """You are an expert legal evaluator. Compare the generated answer to the
ground truth answer and determine:

1. **Correct**: Does the generated answer convey the same key information as the ground truth?
   Minor differences in wording are acceptable. The core legal points must match.
2. **Grounded**: Is the generated answer supported by the provided context passages?
   The answer should not contain information that cannot be traced to the context.

Ground Truth Answer:
{expected_answer}

Generated Answer:
{generated_answer}

Retrieved Context:
{context}

Respond in exactly this JSON format (no other text):
{{"correct": true/false, "grounded": true/false, "reasoning": "brief explanation"}}"""
