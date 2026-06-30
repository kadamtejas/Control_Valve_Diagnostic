"""
build_embeddings.py — one-time (re-run when chatbot_knowledge.md changes).

Chunks the knowledge base, embeds every chunk via the HuggingFace Inference
API, and writes two artifacts next to chatbot_knowledge.md:
    knowledge_vectors.npy   — (n_chunks, 384) float32 matrix
    knowledge_chunks.json   — chunk text + headings (paired with the vectors)

Run from the POC root:
    python build_embeddings.py

Requires HF_API_TOKEN in .env (already loaded from the POC root).
"""
import sys
from pathlib import Path

from dotenv import load_dotenv

POC_ROOT = Path(__file__).resolve().parent
load_dotenv(POC_ROOT / ".env")                       # picks up HF_API_TOKEN
sys.path.insert(0, str(POC_ROOT / "dashboard"))       # so we can import chatbot_rag

import chatbot_rag as rag                             # noqa: E402


def main():
    print("=" * 60)
    print("Building knowledge embeddings for the chatbot")
    print("=" * 60)

    # 1) Smoke test — one short string, confirm HF + token work before the full run
    print("\n[1/3] HF smoke test (embedding one test string)...")
    try:
        v = rag.embed(["control valve stiction test"])
        print(f"      OK — got a {v.shape[1]}-dim vector. HF token + model work.")
    except Exception as e:
        print(f"      FAILED: {e}")
        print("      → Check HF_API_TOKEN in .env, and that the token has "
              "'Make calls to Inference Providers' permission.")
        sys.exit(1)

    # 2) Show the chunk split
    print("\n[2/3] Chunking chatbot_knowledge.md...")
    md = rag.KNOWLEDGE_PATH.read_text(encoding="utf-8")
    chunks = rag.chunk_knowledge(md)
    print(f"      {len(chunks)} chunks:")
    for i, c in enumerate(chunks):
        print(f"        {i:>2}  {c['heading'][:55]}")

    # 3) Build + save
    print("\n[3/3] Embedding all chunks and saving artifacts...")
    info = rag.build_index()
    print(f"      Done. {info['n_chunks']} chunks, {info['dim']}-dim vectors.")
    print(f"      vectors -> {info['vectors']}")
    print(f"      meta    -> {info['meta']}")
    print("\nNext: restart uvicorn so main.py picks up the new index.")


if __name__ == "__main__":
    main()
