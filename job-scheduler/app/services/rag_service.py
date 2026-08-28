"""
==============================================================================
Service: RAG 知識庫服務 (Retrieval-Augmented Generation Service) — v2.6
==============================================================================
ZH: 用途：支撐「平台導覽／客服」浮動助手的知識檢索。
    - 讀取 knowledge/*.md → 切塊 → 以 Ollama 產生向量 → 存入 knowledge_chunks 表
    - 查詢時：問題轉向量 → 與所有片段算 cosine → 取 top-k → 組成 system prompt 上下文
    刻意走「直接打 Ollama」(不經 Portkey)，讓客服助手在 Portkey 掛掉時仍可用；
    embeddings 走 /api/embeddings，對話走 /v1/chat/completions (OpenAI 相容)。

EN: Purpose: Knowledge retrieval backing the floating "platform guide / support"
    assistant.
    - Load knowledge/*.md → chunk → embed via Ollama → store in knowledge_chunks
    - On query: embed question → cosine vs all chunks → top-k → build context
    Deliberately talks to Ollama directly (not through Portkey) so the support
    assistant keeps working even if Portkey is down. Embeddings use
    /api/embeddings; chat uses /v1/chat/completions (OpenAI-compatible).

ZH: 規模備註：知識庫為平台 FAQ／使用說明，量小（數十～數百片段），故直接全載入
    記憶體做暴力 cosine 即可，無需向量資料庫。若未來知識量級成長，再換 FAISS/pgvector。
EN: Scale note: the KB is platform FAQ/usage docs — small (tens to hundreds of
    chunks) — so a brute-force in-memory cosine over all rows is fine; no vector
    DB needed. Swap to FAISS/pgvector only if the corpus grows substantially.
==============================================================================
"""

from __future__ import annotations

import glob
import json
import logging
import math
import os
import re

import httpx
from sqlalchemy.orm import Session

from .. import models, crud
from ..config import settings

logger = logging.getLogger(__name__)


# ==============================================================================
# ZH: 純函式區（無 I/O，可獨立單元測試）| EN: Pure helpers (no I/O, unit-testable)
# ==============================================================================

def chunk_markdown(text: str, source: str, max_chars: int = 600) -> list[dict]:
    """
    ZH: 將 markdown 依「標題段落」切塊，每塊附帶最近的標題（供引用/定位）。
        段落以空行分隔，累積到接近 max_chars 即切一塊；過長的單段再硬切。
    EN: Split markdown into chunks by heading sections; each chunk carries the
        nearest heading (for citation). Paragraphs split on blank lines, grouped
        up to ~max_chars; an over-long single paragraph is hard-split.

    回傳 | returns: [{"source", "heading", "content"}]

    @node job-scheduler/app/services/rag_service.py::chunk_markdown
    """
    chunks: list[dict] = []
    heading = ""
    buf: list[str] = []
    buf_len = 0

    def flush():
        """@node job-scheduler/app/services/rag_service.py::chunk_markdown.<nested@64>.flush"""
        nonlocal buf, buf_len
        body = "\n".join(buf).strip()
        if body:
            chunks.append({"source": source, "heading": heading, "content": body})
        buf = []
        buf_len = 0

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        m = re.match(r"^#{1,6}\s+(.*)$", line)
        if m:
            # ZH: 遇到新標題先收掉前一塊 | EN: new heading → flush previous chunk
            flush()
            heading = m.group(1).strip()
            continue

        if line.strip() == "":
            if buf_len >= max_chars:
                flush()
            else:
                buf.append("")  # ZH: 保留段落間距 | EN: keep paragraph spacing
            continue

        # ZH: 單行就超過上限 → 硬切 | EN: a single line exceeds the cap → hard split
        while len(line) > max_chars:
            buf.append(line[:max_chars])
            flush()
            line = line[max_chars:]

        buf.append(line)
        buf_len += len(line) + 1
        if buf_len >= max_chars:
            flush()

    flush()
    return chunks


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """ZH: 純 Python cosine 相似度 | EN: Pure-Python cosine similarity.

    @node job-scheduler/app/services/rag_service.py::cosine_similarity
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def rank_chunks(
    query_vec: list[float],
    candidates: list[tuple],
    top_k: int,
    min_score: float = 0.0,
) -> list[dict]:
    """
    ZH: 對 (chunk, embedding) 候選做排序，回傳分數最高的 top_k。
    EN: Rank (chunk, embedding) candidates, return the top_k by score.

    candidates: [(chunk_obj, embedding_list), ...]
    回傳 | returns: [{"chunk": obj, "score": float}, ...]  已依分數遞減排序

    @node job-scheduler/app/services/rag_service.py::rank_chunks
    """
    scored = [
        {"chunk": chunk, "score": cosine_similarity(query_vec, emb)}
        for chunk, emb in candidates
    ]
    scored = [s for s in scored if s["score"] >= min_score]
    scored.sort(key=lambda s: s["score"], reverse=True)
    return scored[:top_k]


def build_context_block(ranked: list[dict]) -> str:
    """
    ZH: 把檢索到的片段組成給 LLM 的「知識上下文」字串（含來源標註）。
    EN: Assemble retrieved chunks into a knowledge-context string for the LLM
        (with source tags).

    @node job-scheduler/app/services/rag_service.py::build_context_block
    """
    parts = []
    for i, item in enumerate(ranked, start=1):
        c = item["chunk"]
        tag = c.source if not c.heading else f"{c.source} › {c.heading}"
        parts.append(f"[資料 {i} | {tag}]\n{c.content}")
    return "\n\n".join(parts)


# ZH: 客服／導覽助手的人格與規則（檢索上下文會被插入 {context}）
# EN: Persona + rules for the support/guide assistant ({context} is injected)
GUIDE_SYSTEM_PROMPT = """你是「銘傳大學圖書館 AI 基地」平台的線上客服助手，名字叫「小基」。
你的任務是引導使用者操作這個平台、回答常見問題（如同客服）。

# 回答規則
1. 只根據下方「平台知識」內容回答。知識沒提到的，就誠實說「這部分我不確定，建議聯絡管理員或到問題回報」，不要編造。
2. **用使用者提問的那個語言回答**（他用英文問就用英文答，日文問就用日文答）。
   ⚠ 用中文回答時**一律繁體中文，不可以出現簡體字**。
   知識庫是中文寫的，但那只是資料 —— 不要因為資料是中文就改用中文回答。
3. 親切口語、條列步驟；操作類問題請給「一步一步」的指引。
4. 回答精簡，先給結論/步驟，必要時再補充。不要長篇大論。
5. 若使用者問的與本平台無關（例如寫作業、寫程式），禮貌說明你是平台客服，並引導他到對應功能（例如「AI 助手」分頁的文字聊天）。

# 平台知識（檢索自官方文件，這是你唯一的事實來源）
{context}
"""

GUIDE_NO_CONTEXT_PROMPT = """你是「銘傳大學圖書館 AI 基地」平台的線上客服助手「小基」。
目前知識庫尚未建立或查無相關資料。請禮貌告知使用者：你暫時找不到對應的說明，
建議他到「問題回報」或聯絡管理員。不要編造平台功能。
**用使用者提問的那個語言回答**；用中文時一律繁體，不可以出現簡體字。"""


# ZH: v2.6 程式家教模式人格（用於 Notebook/Lab 的程式指導）。
#     {file_block} 為使用者「手動挑選附上」的程式碼（可能為空）；{context} 為檢索到的平台說明。
# EN: v2.6 code-tutor persona for Notebook/Lab coding help. {file_block} is the
#     user-attached code (may be empty); {context} is retrieved platform docs.
CODE_TUTOR_SYSTEM_PROMPT = """你是「銘傳大學圖書館 AI 基地」的程式家教，名字叫「小基」。
你陪伴學生在 Notebook / Lab（code-server）裡學寫程式。

# 教學風格
1. 像家教，不是答案機：先點出問題所在與「為什麼」，引導學生思考，再給可執行的修正。
2. 看得到學生附上的程式碼時，針對該檔具體說明（指出行為、錯誤原因、改法）；附上修正後的關鍵片段即可，不用整份重貼。
3. **用學生提問的那個語言回答**；用中文時一律繁體，不可以出現簡體字。
   親切清楚；程式碼用 ``` 區塊。先講重點，必要時再延伸。
4. 若問題其實是「平台怎麼操作」（如怎麼開 Lab、裝套件、提交運算任務），改用下方「平台知識」回答或引導對應功能。
5. 不確定就老實說，不要編造 API 或平台功能。

# 學生附上的程式碼（可能為空）
{file_block}

# 平台知識（檢索自官方文件，操作類問題以此為準）
{context}
"""


# ==============================================================================
# ZH: I/O 區 — Ollama 呼叫 | EN: I/O — Ollama calls
# ==============================================================================

async def embed_text(text: str) -> list[float]:
    """
    ZH: 以 Ollama /api/embeddings 取得單段文字的向量。失敗回傳空陣列。
    EN: Get an embedding for one text via Ollama /api/embeddings. Returns [] on failure.

    @node job-scheduler/app/services/rag_service.py::embed_text
    """
    url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/embeddings"
    payload = {"model": settings.RAG_EMBED_MODEL, "prompt": text}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                logger.error("Ollama embeddings returned %s: %s", resp.status_code, resp.text[:200])
                return []
            data = resp.json()
            return data.get("embedding", []) or []
    except httpx.HTTPError as e:
        logger.error("Ollama embeddings request failed: %s", e)
        return []


# ==============================================================================
# ZH: 知識庫匯入 | EN: Knowledge base ingestion
# ==============================================================================

async def ingest_knowledge_base(db: Session, *, force: bool = False) -> dict:
    """
    ZH: 讀取 KNOWLEDGE_DIR 下所有 .md → 切塊 → embedding → 重建 knowledge_chunks。
        force=False 且已有資料時略過（啟動時用）；force=True 一律重建（admin /reindex）。
    EN: Read all .md under KNOWLEDGE_DIR → chunk → embed → rebuild knowledge_chunks.
        force=False skips when data already exists (startup); force=True rebuilds
        unconditionally (admin /reindex).

    @node job-scheduler/app/services/rag_service.py::ingest_knowledge_base
    """
    existing = db.query(models.KnowledgeChunk).count()
    if existing and not force:
        logger.info("RAG: knowledge base already has %d chunks, skip ingest", existing)
        return {"status": "skipped", "chunks": existing}

    kb_dir = settings.KNOWLEDGE_DIR
    md_files = sorted(glob.glob(os.path.join(kb_dir, "**", "*.md"), recursive=True))
    if not md_files:
        logger.warning("RAG: no .md files found under %s", kb_dir)
        return {"status": "empty", "chunks": 0, "files": 0}

    # ZH: 清空舊資料後重建 | EN: clear then rebuild
    db.query(models.KnowledgeChunk).delete()
    db.commit()

    total = 0
    failed = 0
    for path in md_files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            logger.error("RAG: cannot read %s: %s", path, e)
            continue

        source = os.path.relpath(path, kb_dir).replace(os.sep, "/")
        for ck in chunk_markdown(text, source):
            vec = await embed_text(_embed_input(ck))
            if not vec:
                failed += 1
                continue
            db.add(models.KnowledgeChunk(
                source=ck["source"],
                heading=ck["heading"],
                content=ck["content"],
                embedding=json.dumps(vec),
            ))
            total += 1
        db.commit()

    logger.info("RAG: ingested %d chunks from %d files (%d embed failures)", total, len(md_files), failed)
    return {"status": "ok", "chunks": total, "files": len(md_files), "failed": failed}


def _embed_input(chunk: dict) -> str:
    """ZH: 嵌入時把標題併入內容，提升檢索命中 | EN: Prepend heading to improve recall.

    @node job-scheduler/app/services/rag_service.py::_embed_input
    """
    h = chunk.get("heading") or ""
    return f"{h}\n{chunk['content']}" if h else chunk["content"]


# ==============================================================================
# ZH: 檢索 | EN: Retrieval
# ==============================================================================

async def retrieve(db: Session, query: str) -> list[dict]:
    """
    ZH: 對使用者問題做檢索，回傳 top-k 片段（含分數）。查無/失敗回傳 []。
    EN: Retrieve top-k chunks for the user's question. Returns [] when empty/failed.

    @node job-scheduler/app/services/rag_service.py::retrieve
    """
    qvec = await embed_text(query)
    if not qvec:
        return []

    rows = db.query(models.KnowledgeChunk).all()
    candidates = []
    for r in rows:
        try:
            emb = json.loads(r.embedding) if r.embedding else []
        except (json.JSONDecodeError, TypeError):
            emb = []
        if emb:
            candidates.append((r, emb))

    # v3.1 step 6：top_k / min_score 改 runtime 讀 SystemConfig（admin 可即時調），.env 為 fallback
    top_k = crud.get_setting(db, "rag_top_k")
    min_score = crud.get_setting(db, "rag_min_score")
    return rank_chunks(qvec, candidates, top_k, min_score)


# ==============================================================================
# ZH: 回答語言 —— 伺服器端判定，不靠模型自己看
# ==============================================================================
# ZH: 🔴 為什麼需要這個：提示詞裡已經寫了「用使用者提問的那個語言回答」，
#     但實測 qwen2.5:7b **問英文照樣用中文回答**（日文問句它倒是守住了）。
#     失敗模式很一致 —— 檢索到的知識庫全是中文，模型被上下文帶著走，
#     預設回中文。這對國際學生是實質障礙：他問英文，得到一整段看不懂的中文。
#
# ZH: 所以判定改在伺服器端做，並把結論**當成一條硬指令**塞進 system prompt。
#     只判「是不是中文」這一件事就夠 —— 真正要壓的是「不要預設回中文」，
#     至於他講的是英文、越南文還是印尼文，交給模型照抄提問語言即可
#     （列舉語言清單一定會漏，而漏掉的那個人只會拿到中文）。
#
# ZH: ⚠ 判定看**書寫系統**不看字詞：假名／諺文出現就不是中文；
#     完全沒有 CJK 漢字也不是中文。中日文都用漢字，所以假名要先判。
_KANA_HANGUL = re.compile(r"[぀-ヿ가-힯]")
_HAN = re.compile(r"[一-鿿]")


def is_chinese_query(text: str) -> bool:
    """
    ZH: 這句提問是不是中文。

    ZH: 規則：有假名或諺文 → 不是中文（日／韓）；否則有漢字 → 是中文；
        都沒有 → 不是中文（英文與其他拉丁語系、泰文、俄文…）。

    @node job-scheduler/app/services/rag_service.py::is_chinese_query
    """
    t = text or ""
    if _KANA_HANGUL.search(t):
        return False
    return bool(_HAN.search(t))


# ZH: 依書寫系統認得出來的語言。**點名比泛指有效** —— 實測：對日文提問，
#     說「用使用者提問的那個語言」→ 0/2 用日文回答（都回英文）；
#     說「Reply in Japanese」→ 2/2 用日文回答。
# ZH: ⚠ 只列**靠書寫系統就分得出來**的。拉丁字母那一大票（英文、印尼文、
#     西班牙文…）分不出來，就退回泛指 —— 實測那種情況模型會回英文，
#     對國際學生是可接受的落點。
# ZH: 越南文用 đ/ơ/ư 判：那三個字母是越南文特有的（ă/â/ê 在羅馬尼亞文、
#     法文裡也有，不能用）。
_NAMED_SCRIPTS = [
    ("Japanese",   re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")),
    ("Korean",     re.compile(r"[\uac00-\ud7af\u1100-\u11ff]")),
    ("Thai",       re.compile(r"[\u0e00-\u0e7f]")),
    ("Russian",    re.compile(r"[\u0400-\u04ff]")),
    ("Arabic",     re.compile(r"[\u0600-\u06ff]")),
    ("Hindi",      re.compile(r"[\u0900-\u097f]")),
    ("Vietnamese", re.compile(r"[đĐơƠưƯ]")),
]


def detect_named_language(text: str) -> str | None:
    """
    ZH: 認得出來就回語言名（英文寫法，要塞進提示詞），認不出來回 None。

    ZH: ⚠ 順序有意義：日文與中文都用漢字，所以**假名要先判**。
        越南文放最後 —— 它的判準是拉丁字母，最寬鬆。

    @node job-scheduler/app/services/rag_service.py::detect_named_language
    """
    t = text or ""
    for name, pat in _NAMED_SCRIPTS:
        if pat.search(t):
            return name
    return "Traditional Chinese" if _HAN.search(t) else None


def language_directive(query: str) -> str:
    """
    ZH: 依提問語言回傳一行要插進 system prompt 的硬指令。

    ZH: 🔴 **泛指沒有用，一定要點名。** 實測見 scripts/bench_reply_language.py：
        說「用使用者提問的那個語言回答」時，日文提問 0/2 回日文（都回英文）；
        改成「Reply in Japanese」之後 2/2。

    ZH: ⚠ 這條對舊的 `qwen2.5:7b` **完全沒有作用**（英文提問 0/15 回英文，
        四種擺放位置都試過，連把檢索上下文換成全英文也一樣）。
        2026-08-28 RAG_CHAT_MODEL 因此換成 llama3。

    @node job-scheduler/app/services/rag_service.py::language_directive
    """
    lang = detect_named_language(query)
    if lang == "Traditional Chinese":
        return ("\n\n# 回答語言（最高優先）\n"
                "使用者用中文提問 → 用**繁體中文**回答。**不可以出現簡體字。**")
    if lang:
        return ("\n\n# Reply language (highest priority)\n"
                f"Reply in **{lang}**. The user asked in {lang}, so the entire answer "
                "must be written in that language. Do NOT answer in English or Chinese. "
                "Keep on-screen button and page names in their original Chinese, "
                "followed by a short gloss in the answer language the first time each appears.")
    # ZH: 認不出來（多半是英文或其他拉丁語系）—— 泛指，模型實測會回英文。
    return ("\n\n# Reply language (highest priority)\n"
            "Reply in exactly the same language as the user's question. "
            "Do NOT reply in Chinese — the platform knowledge below is written in "
            "Chinese, but that is reference data, not the language to answer in. "
            "Keep on-screen button and page names in their original Chinese, "
            "followed by an English gloss in parentheses the first time each appears.")


def build_messages(query: str, ranked: list[dict], history: list[dict] | None = None,
                   history_turns: int | None = None) -> list[dict]:
    """
    ZH: 組裝送給 Ollama 的 messages：system(含檢索上下文) + (歷史) + 本次提問。
        history_turns 由呼叫端(有 db)傳入 runtime 值；None 時回退 .env 預設。
    EN: Build the messages for Ollama. history_turns is the runtime value passed by the
        caller (which has db); falls back to the .env default when None.

    @node job-scheduler/app/services/rag_service.py::build_messages
    """
    if ranked:
        system = GUIDE_SYSTEM_PROMPT.format(context=build_context_block(ranked))
    else:
        system = GUIDE_NO_CONTEXT_PROMPT
    # ZH: 語言指令的擺放位置由 scripts/bench_reply_language.py 的實測決定，見該檔。
    system += language_directive(query)

    turns = history_turns if history_turns is not None else settings.RAG_HISTORY_TURNS
    msgs = [{"role": "system", "content": system}]
    if history:
        # ZH: 只保留最近數輪，避免上下文爆量 | EN: keep only recent turns
        msgs += history[-(turns * 2):]
    msgs.append({"role": "user", "content": query})
    return msgs


def build_code_messages(
    query: str,
    ranked: list[dict],
    file_excerpt: dict | None = None,
    history: list[dict] | None = None,
    history_turns: int | None = None,
) -> list[dict]:
    """
    ZH: 組裝「程式家教」模式的 messages：system(家教人格 + 附檔 + 檢索上下文) + 歷史 + 提問。
    EN: Build messages for code-tutor mode: system(tutor persona + attached file +
        retrieved context) + history + question.

    file_excerpt: {"path": str, "content": str, "truncated": bool} 或 None

    @node job-scheduler/app/services/rag_service.py::build_code_messages
    """
    if file_excerpt and file_excerpt.get("content"):
        trunc = "（內容過長，僅節錄前段）\n" if file_excerpt.get("truncated") else ""
        file_block = f"檔案：{file_excerpt.get('path', '')}\n{trunc}```\n{file_excerpt['content']}\n```"
    else:
        file_block = "（學生這次沒有附上程式碼）"

    context = build_context_block(ranked) if ranked else "（無相關平台說明）"
    system = CODE_TUTOR_SYSTEM_PROMPT.format(file_block=file_block, context=context)
    # ZH: 家教模式同樣要跟著提問語言 —— 國際學生也會用這一邊。
    system += language_directive(query)

    turns = history_turns if history_turns is not None else settings.RAG_HISTORY_TURNS
    msgs = [{"role": "system", "content": system}]
    if history:
        msgs += history[-(turns * 2):]
    msgs.append({"role": "user", "content": query})
    return msgs
