#chunking_comparison.py
import json
import yaml
import fitz  # PyMuPDF
import numpy as np
import pandas as pd
import time
from pathlib import Path
from llama_index.core import Settings, VectorStoreIndex, Document
from llama_index.core.node_parser import (
    SentenceWindowNodeParser,
    SemanticSplitterNodeParser,
    TokenTextSplitter,
)
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

# 1. Directory Paths Setup
script_dir = Path(__file__).resolve().parent
hw03_dir = script_dir.parent / "reports" / "hw03"
data_dir = hw03_dir / "data"
raw_dir = hw03_dir / "raw"
raw_dir.mkdir(parents=True, exist_ok=True)

# 2. Load Questions from questions.yaml
questions_yaml_path = script_dir / "questions.yaml"
if not questions_yaml_path.exists():
    questions_yaml_path = hw03_dir / "questions.yaml"

with open(questions_yaml_path, "r", encoding="utf-8") as f:
    yaml_content = yaml.safe_load(f)
    questions_data = yaml_content.get("questions", [])

# 3. Document Extraction via PyMuPDF
pdf_files = list(data_dir.glob("*.pdf"))
documents = []

for pdf_path in pdf_files:
    doc = fitz.open(pdf_path)
    full_text = ""
    for page in doc:
        full_text += page.get_text() + "\n"
    
    documents.append(
        Document(
            text=full_text,
            metadata={"file_name": pdf_path.name}
        )
    )

print(f"[+] Loaded {len(documents)} document(s) with {sum(len(d.text) for d in documents)} total characters.")

# 4. Embedding Model Setup
embed_model = HuggingFaceEmbedding(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)
Settings.embed_model = embed_model

# 5. Build Chunkers & Vector Indices
token_splitter = TokenTextSplitter(chunk_size=256, chunk_overlap=50)
token_nodes = token_splitter.get_nodes_from_documents(documents)
token_index = VectorStoreIndex(token_nodes, embed_model=embed_model)

semantic_splitter = SemanticSplitterNodeParser(
    buffer_size=1, embed_model=embed_model
)
semantic_nodes = semantic_splitter.get_nodes_from_documents(documents)
semantic_index = VectorStoreIndex(semantic_nodes, embed_model=embed_model)

sentence_window_parser = SentenceWindowNodeParser.from_defaults(
    window_size=3,
    window_metadata_key="window",
    original_text_metadata_key="original_sentence",
)
sentence_nodes = sentence_window_parser.get_nodes_from_documents(documents)
sentence_index = VectorStoreIndex(sentence_nodes, embed_model=embed_model)


# 6. Helper Functions
def cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
    return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))


def evaluate_technique(q_item: dict, technique_name: str, index: VectorStoreIndex, k: int = 5):
    query_id = q_item.get("id")
    query_text = q_item.get("question")
    expected_ans = q_item.get("expected_answer")
    expected_src = q_item.get("expected_source")

    query_emb = np.array(embed_model.get_query_embedding(query_text))
    retriever = index.as_retriever(similarity_top_k=k)

    # Measure retrieval latency only
    start_time = time.perf_counter()
    results = retriever.retrieve(query_text)
    latency_ms = (time.perf_counter() - start_time) * 1000

    records = []

    for idx, result in enumerate(results, start=1):
        content = result.node.get_content()
        doc_emb = np.array(embed_model.get_text_embedding(content))
        cos_sim = cosine_similarity(query_emb, doc_emb)
        preview_text = content[:160].replace("\n", " ").strip() + "..."

        # Determine source document
        source_file = result.node.metadata.get("file_name")

        records.append({
            "question_id": query_id,
            "query": query_text,
            "expected_answer": expected_ans,
            "expected_source": expected_src,
            "technique": technique_name,
            "rank": idx,
            "store_score": round(result.score, 4) if result.score is not None else None,
            "cosine_sim": round(cos_sim, 4),
            "chunk_len": len(content),
            "source_file": source_file,
            "retrieval_latency_ms": round(latency_ms, 2),
            "preview": preview_text
        })

    return records


# 7. Run Evaluations for All Questions across All Techniques
pipelines = [
    ("Token", token_index),
    ("Semantic", semantic_index),
    ("Sentence-Window", sentence_index)
]

all_records = []

for q_item in questions_data:
    q_id = q_item.get("id")
    q_text = q_item.get("question")

    print("\n" + "#" * 100)
    print(f"QUESTION ID: {q_id} | QUERY: {q_text}")
    print("#" * 100)

    for technique, index in pipelines:
        records = evaluate_technique(q_item, technique, index, k=5)
        all_records.extend(records)

        # Print Output Table per question, per technique
        df_technique = pd.DataFrame(records)[["rank", "store_score", "cosine_sim", "chunk_len", "preview"]]
        print("\n" + "=" * 80)
        print(f"TECHNIQUE: {technique}")
        print("=" * 80)
        print(df_technique.to_string(index=False))


# 8. Save Machine-Readable Output to raw/
csv_path = raw_dir / "retrieval_results.csv"
json_path = raw_dir / "retrieval_results.json"

df_all = pd.DataFrame(all_records)
df_all.to_csv(csv_path, index=False)

with open(json_path, "w", encoding="utf-8") as f:
    json.dump(all_records, f, indent=2)

# 9. Generate Summary Metrics
df_all = pd.DataFrame(all_records)

summary_rows = []

for technique in ["Token", "Semantic", "Sentence-Window"]:

    technique_df = df_all[df_all["technique"] == technique]

    # Number of chunks produced
    if technique == "Token":
        num_chunks = len(token_nodes)
        avg_chunk_length = np.mean([len(n.get_content()) for n in token_nodes])
    elif technique == "Semantic":
        num_chunks = len(semantic_nodes)
        avg_chunk_length = np.mean([len(n.get_content()) for n in semantic_nodes])
    else:
        num_chunks = len(sentence_nodes)
        avg_chunk_length = np.mean([len(n.get_content()) for n in sentence_nodes])

    # Top-1 cosine and Mean@5 cosine
    top1_values = (
        technique_df[technique_df["rank"] == 1]["cosine_sim"]
        .dropna()
    )

    mean_cosine = technique_df["cosine_sim"].mean()

    # Recall@5:
    # Did the expected source appear in the retrieved top-5?
    recall_values = []

    for question_id in questions_data:
        q_id = question_id.get("id")
        expected_source = question_id.get("expected_source")

        q_results = technique_df[
            technique_df["question_id"] == q_id
        ]

        retrieved_sources = q_results["source_file"].dropna().tolist()

        recall = 1 if expected_source in retrieved_sources else 0
        recall_values.append(recall)

    recall_at_k = np.mean(recall_values)

    # Mean retrieval latency
    latency = (
        technique_df
        .groupby("question_id")["retrieval_latency_ms"]
        .first()
        .mean()
    )

    summary_rows.append({
        "Technique": technique,
        "Chunks": num_chunks,
        "Avg chunk length": round(avg_chunk_length, 2),
        "Top-1 cosine": round(top1_values.mean(), 4),
        "Mean@5 cosine": round(mean_cosine, 4),
        "Recall@5": round(recall_at_k, 4),
        "Mean retrieval latency (ms)": round(latency, 2)
    })

summary_df = pd.DataFrame(summary_rows)

print("\n" + "=" * 100)
print("CHUNKING TECHNIQUE COMPARISON")
print("=" * 100)
print(summary_df.to_string(index=False))

# Save summary
summary_path = raw_dir / "summary_metrics.csv"
summary_df.to_csv(summary_path, index=False)

print(f"\n[+] Saved summary metrics to: {summary_path}")

print(f"\n[+] Saved full evaluation dataset ({len(all_records)} total retrieval rows) to:\n  - {csv_path}\n  - {json_path}")