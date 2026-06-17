"""
==============================================================================
ZH: rag_service 純邏輯單元測試（不需 Ollama / DB）
EN: Unit tests for rag_service pure logic (no Ollama / DB needed)
==============================================================================
ZH: 測試切塊、cosine、排序、上下文組裝。可用 pytest 或直接 `python test_rag_service.py`。
EN: Tests chunking, cosine, ranking, context build. Run via pytest or directly.
==============================================================================
"""

import os
import sys

# ZH: config 啟動時會驗證祕鑰強度，先注入合法值，import 才不會 fail-fast
# EN: config validates secret strength on load; inject valid values before import
os.environ.setdefault("JWT_SECRET_KEY", "x" * 40)
os.environ.setdefault("WORKER_API_TOKEN", "y" * 20)
os.environ.setdefault("SECRETS_MASTER_KEY", "z" * 40)

# ZH: 讓 `import app...` 找得到 job-scheduler 套件 | EN: put job-scheduler on sys.path
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(_HERE, "..", "job-scheduler")))

from app.services import rag_service as rs  # noqa: E402


# ---- ZH: 假 chunk 物件（模仿 KnowledgeChunk 屬性）| EN: fake chunk obj ----
class FakeChunk:
    def __init__(self, source, heading, content):
        self.source = source
        self.heading = heading
        self.content = content


def test_chunk_markdown_attaches_heading():
    md = "# 登入\n第一段內容。\n\n# 運算任務\n第二段內容。"
    chunks = rs.chunk_markdown(md, "10-登入.md")
    headings = {c["heading"] for c in chunks}
    assert "登入" in headings
    assert "運算任務" in headings
    assert all(c["source"] == "10-登入.md" for c in chunks)


def test_chunk_markdown_respects_max_chars():
    body = "句子。" * 500  # 遠超 max_chars
    chunks = rs.chunk_markdown("# 標題\n" + body, "big.md", max_chars=200)
    assert len(chunks) > 1
    assert all(len(c["content"]) <= 250 for c in chunks)  # 容許切塊邊界誤差


def test_cosine_identical_and_orthogonal():
    assert abs(rs.cosine_similarity([1.0, 0.0], [1.0, 0.0]) - 1.0) < 1e-9
    assert abs(rs.cosine_similarity([1.0, 0.0], [0.0, 1.0]) - 0.0) < 1e-9


def test_cosine_handles_bad_input():
    assert rs.cosine_similarity([], [1.0]) == 0.0
    assert rs.cosine_similarity([1.0, 2.0], [1.0]) == 0.0      # 長度不符
    assert rs.cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0  # 零向量


def test_rank_chunks_sorts_and_filters():
    q = [1.0, 0.0]
    near = FakeChunk("a.md", "近", "x")
    far = FakeChunk("b.md", "遠", "y")
    candidates = [
        (far, [0.0, 1.0]),    # cosine 0
        (near, [0.9, 0.1]),   # cosine 高
    ]
    ranked = rs.rank_chunks(q, candidates, top_k=2, min_score=0.1)
    assert len(ranked) == 1            # far 被 min_score 濾掉
    assert ranked[0]["chunk"] is near


def test_rank_chunks_top_k_limit():
    q = [1.0, 0.0]
    candidates = [(FakeChunk(f"{i}.md", "", ""), [1.0, 0.0]) for i in range(5)]
    ranked = rs.rank_chunks(q, candidates, top_k=3, min_score=0.0)
    assert len(ranked) == 3


def test_build_context_block_tags_sources():
    ranked = [
        {"chunk": FakeChunk("10-登入.md", "如何登入", "點按鈕"), "score": 0.9},
        {"chunk": FakeChunk("20-運算任務.md", "", "提交任務"), "score": 0.8},
    ]
    block = rs.build_context_block(ranked)
    assert "10-登入.md › 如何登入" in block
    assert "20-運算任務.md" in block
    assert "點按鈕" in block


def test_build_messages_uses_context_when_present():
    ranked = [{"chunk": FakeChunk("10-登入.md", "登入", "點按鈕登入"), "score": 0.9}]
    msgs = rs.build_messages("怎麼登入", ranked, history=[])
    assert msgs[0]["role"] == "system"
    assert "點按鈕登入" in msgs[0]["content"]
    assert msgs[-1] == {"role": "user", "content": "怎麼登入"}


def test_build_messages_falls_back_without_context():
    msgs = rs.build_messages("隨便問", [], history=[])
    assert msgs[0]["role"] == "system"
    assert "知識庫" in msgs[0]["content"]  # 無上下文時的 fallback prompt


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
            except AssertionError as e:
                failures += 1
                print(f"  FAIL  {name}: {e}")
            except Exception as e:  # noqa: BLE001
                failures += 1
                print(f"  ERROR {name}: {type(e).__name__}: {e}")
    print(f"\n{'OK' if failures == 0 else f'{failures} FAILED'}")
    sys.exit(1 if failures else 0)
