"""
chatbot_rag.py — lightweight RAG retrieval over chatbot_knowledge.md.

Two phases:
  • BUILD TIME (run build_embeddings.py once, re-run when knowledge.md changes):
    chunk the knowledge file by heading, embed each chunk via the HuggingFace
    Inference API, and save vectors (.npy) + chunk text (.json) to disk.
  • QUERY TIME (called from main.py on every chat message):
    embed the user's question, cosine-match against the saved chunk vectors,
    return only the top-k relevant chunk texts.

Safety: every failure path (no token, HF down, no index built yet, nothing
relevant) returns None, and the caller falls back to injecting the full
knowledge file — so the chatbot never breaks because of RAG.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import numpy as np

# ── Paths (mirror main.py's BASE_DIR logic) ──────────────────────────────────
if os.environ.get("VALVE_BASE_DIR"):
    POC_ROOT = Path(os.environ["VALVE_BASE_DIR"])
else:
    POC_ROOT = Path(__file__).resolve().parent.parent   # dashboard/ -> POC root

KNOWLEDGE_PATH  = POC_ROOT / "chatbot_knowledge.md"
INDEX_VEC_PATH  = POC_ROOT / "knowledge_vectors.npy"
INDEX_META_PATH = POC_ROOT / "knowledge_chunks.json"

# ── HuggingFace embedding config ─────────────────────────────────────────────
HF_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
HF_URL   = f"https://router.huggingface.co/hf-inference/models/{HF_MODEL}/pipeline/feature-extraction"
TOP_K     = 5
MIN_SCORE = 0.15   # if the best chunk scores below this, fall back to full file


# ── Chunking ─────────────────────────────────────────────────────────────────
def chunk_knowledge(md_text: str) -> list[dict]:
    """Split knowledge.md at every ## / ### heading.

    - The title preamble (before the first heading) is dropped.
    - Each ### sub-section is prefixed with its parent ## section name so it is
      self-describing when retrieved on its own.
    Returns: [{"heading": str, "text": str}, ...]
    """
    import re

    lines = md_text.splitlines(keepends=True)
    chunks: list[dict] = []
    cur_lines: list[str] = []
    cur_head: str | None = None
    cur_level: int | None = None
    parent_h2: str | None = None

    def flush():
        if cur_head and cur_lines:
            body = "".join(cur_lines).strip()
            if cur_level == 3 and parent_h2:
                text = f"[Section: {parent_h2}]\n{body}"
            else:
                text = body
            chunks.append({"heading": cur_head, "text": text})

    for ln in lines:
        m = re.match(r"^(#{2,3})\s+(.*)", ln)
        if m:
            flush()
            cur_level = len(m.group(1))
            cur_head = m.group(2).strip()
            cur_lines = [ln]
            if cur_level == 2:
                parent_h2 = cur_head
        else:
            cur_lines.append(ln)
    flush()
    return chunks


# ── HuggingFace embedding call ───────────────────────────────────────────────
def _to_matrix(data) -> np.ndarray:
    """Normalise HF response into a 2-D (n, dim) float array.
    Handles pooled sentence vectors (2-D) and token-level output (3-D -> mean).
    """
    arr = np.array(data, dtype=np.float32)
    if arr.ndim == 3:          # (n, tokens, dim) -> mean-pool over tokens
        arr = arr.mean(axis=1)
    if arr.ndim == 1:          # single vector -> (1, dim)
        arr = arr[None, :]
    return arr


def _l2_normalize(arr: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms


def embed(texts: list[str], token: str | None = None, retries: int = 3,
          timeout: float = 30.0) -> np.ndarray:
    """Embed a list of strings via HF Inference API -> normalised (n, dim) array."""
    import httpx  # lazy import; only needed when actually embedding

    token = token or os.environ.get("HF_API_TOKEN")
    if not token:
        raise RuntimeError("HF_API_TOKEN not set (check .env in the POC root).")

    headers = {"Authorization": f"Bearer {token}"}
    last_err = None
    for attempt in range(retries):
        try:
            r = httpx.post(HF_URL, headers=headers,
                           json={"inputs": texts}, timeout=timeout)
            if r.status_code == 503:          # model cold-loading on HF side
                time.sleep(2 + attempt * 2)
                continue
            r.raise_for_status()
            return _l2_normalize(_to_matrix(r.json()))
        except Exception as e:                # noqa: BLE001
            last_err = e
            time.sleep(1 + attempt)
    raise RuntimeError(f"HF embedding failed after {retries} attempts: {last_err}")


# ── Build (offline, run once) ────────────────────────────────────────────────
def build_index(batch: int = 16) -> dict:
    """Chunk knowledge.md, embed all chunks, save vectors + text to disk."""
    md = KNOWLEDGE_PATH.read_text(encoding="utf-8")
    chunks = chunk_knowledge(md)
    texts = [c["text"] for c in chunks]

    vecs = []
    for i in range(0, len(texts), batch):
        vecs.append(embed(texts[i:i + batch]))
    mat = np.vstack(vecs).astype(np.float32)

    np.save(INDEX_VEC_PATH, mat)
    INDEX_META_PATH.write_text(
        json.dumps({"model": HF_MODEL, "chunks": chunks}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"n_chunks": len(texts), "dim": int(mat.shape[1]),
            "vectors": str(INDEX_VEC_PATH), "meta": str(INDEX_META_PATH)}


# ── Query time (cached load + retrieve) ──────────────────────────────────────
_INDEX = None  # process-level cache: {"vectors": np.ndarray, "chunks": list}


def load_index():
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    if not (INDEX_VEC_PATH.exists() and INDEX_META_PATH.exists()):
        return None
    vectors = np.load(INDEX_VEC_PATH)
    meta = json.loads(INDEX_META_PATH.read_text(encoding="utf-8"))
    _INDEX = {"vectors": vectors, "chunks": meta["chunks"]}
    return _INDEX


def retrieve(query: str, k: int = TOP_K, min_score: float = MIN_SCORE):
    """Return top-k relevant chunk texts joined, or None to signal full-file fallback."""
    idx = load_index()
    if idx is None or not query.strip():
        return None
    try:
        qvec = embed([query], retries=1, timeout=6.0)   # fast-fail: user is waiting
    except Exception:
        return None
    sims = idx["vectors"] @ qvec[0]        # cosine (both L2-normalised)
    order = np.argsort(-sims)[:k]
    if len(order) == 0 or float(sims[order[0]]) < min_score:
        return ""   # retrieval worked but nothing relevant -> inject NO knowledge
    return "\n\n".join(idx["chunks"][int(i)]["text"] for i in order)
