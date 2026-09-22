# HW03 Retrieval Quality & Chunking Comparison Report

## 1. Summary Comparison Table

| Technique | Chunks | Avg chunk length | Top-1 cosine | Mean@k cosine | Recall@k | Mean retrieval latency (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Token** | 27 | 1139.63 | 0.6327 | 0.5831 | 1.0 | 9.89 |
| **Semantic** | 7 | 3515.00 | 0.5683 | 0.4825 | 1.0 | 8.63 |
| **Sentence-Window** | 120 | 205.04 | 0.6856 | 0.6075 | 1.0 | 9.74 |

---

## 2. Low-Quality / False Positive Retrieval Analysis

* **Query (Q1):** "What caused SEPTA Trolley 111's pantograph to become entangled with the overhead catenary system on September 25, 2025?"
* **Technique & Rank:** Token Chunking (Rank 1 / Rank 2)
* **Score:** High Cosine Similarity (~0.23–0.45 range)
* **Retrieved Chunk Text:**
> ...the trolley operating along the D Line experienced continuous pantograph wire contact near the Scenic Road crossover where catenary tension inspection logs were missing...
* **Explanation:** The vector embedding model (`sentence-transformers/all-MiniLM-L6-v2`) assigned a high similarity score because the retrieved chunk shares high-frequency domain keywords (`SEPTA`, `pantograph`, `catenary`, `D Line`, `Scenic Road`). However, the chunk only provides background metadata and location details rather than explaining the specific root cause (sagging contact wires and inadequate wire tension).
---
## 3. Observations
Token-based chunking produces fixed-size character splits without respecting natural linguistic boundaries, frequently splitting relevant context across adjacent chunks. Semantic chunking dynamically groups semantically cohesive sentences based on embedding distance thresholds, preserving contextual integrity but occasionally generating unevenly sized chunks. Sentence-window chunking isolates granular individual sentences for targeted vector searching while attaching neighboring contextual sentences (window size = 3) in metadata for synthesis.
Sentence-window retrieval achieves superior semantic precision because sentence-level embeddings minimize vector noise from unrelated surrounding text. Semantic chunking follows closely by maintaining logical narrative flow, whereas Token chunking suffers from arbitrary context truncation.
---
## 4. Conclusion
Sentence-window chunking is the most effective technique for this domain corpus. By embedding single sentences and expanding the context window during retrieval, it maximizes retrieval precision without losing surrounding background details required for complete answer generation.
---
## 5. AI Assistant Reflection & Verification
1. **AI Assistant vs. Independent Contributions:**
   * **AI Assistant:** Used to construct LlamaIndex pipeline scaffolding, generate PyMuPDF parsing loops, build evaluation functions, and format Markdown tables.
   * **Independent Work:** Defined `questions.yaml` domain queries, validated ground-truth facts against `RIR2613.pdf`, debugged environment import errors, and analyzed false-positive retrieval results.

2. **Incorrect / Unsuitable AI-Produced Output:**
   * The AI assistant initially recommended LlamaIndex's default `SimpleDirectoryReader`, which failed to parse the PDF correctly, resulting in a `ModuleNotFoundError` for `llama_index.readers.file` and returning raw binary text stream garbage.

3. **Detection & Verification:**
   * Inspected console output and generated CSV previews, observing raw binary stream encoding symbols (`\x00\x02...`) rather than readable English text from the transit report.

4. **Remediation & Working Solution:**
   * Replaced the default loader with direct PyMuPDF (`fitz.open()`) text extraction, reading PDF streams page-by-page into clean UTF-8 text strings inside LlamaIndex `Document` objects before indexing.
