"""
ZH: 回答語言的實測台 —— 「語言指令要放哪裡」與「哪個對話模型守得住」。

ZH: 這支存在的理由：2026-08-28 我在 rag_service 的註解裡寫了一句
    「語言指令放最後，放前面會被知識區塊淹掉（實測過）」——
    **那句是假的，我沒測過**。改成真的測，並把腳本留下來，
    下一個人才驗得回去（也才有辦法在換模型後重跑）。

ZH: 怎麼跑（要在服務層容器裡，因為它要連 Ollama 與知識庫）：

        docker cp scripts/bench_reply_language.py ai-platform-scheduler:/tmp/
        docker exec -e PYTHONPATH=/app ai-platform-scheduler python /tmp/bench_reply_language.py

ZH: 2026-08-28 的結果（RAG_EMBED_MODEL=bge-m3）：
      · 四種擺放位置 × 英文提問 × 2 次 → `qwen2.5:7b` **8/8 用中文回答**。
        位置無關，換成全英文的檢索上下文也一樣 —— 是模型壓不住，不是提示詞問題。
      · 同樣條件下 `llama3` 2/2 用英文回答，而且會保留中文按鈕名再加英譯。
      · 中文提問時：llama3 漏出的簡體字比 qwen 少，而且**內容更忠於知識庫**
        （qwen 把「教師閒置 120 分鐘」答成「教師無時間限制」）。

ZH: ⚠ 7B 模型的輸出有隨機性，所以每種條件跑兩次。跑一次分不出
    「這個做法不行」與「這次剛好不行」。
"""
import asyncio, json, re, sys
import httpx
from app.database import SessionLocal
from app.config import settings
from app.services import rag_service as R

Q = "How do I submit a training job?"
REPEATS = 2


def cjk_ratio(t):
    han = len(re.findall(r"[\u4e00-\u9fff]", t))
    lat = len(re.findall(r"[A-Za-z]", t))
    return han, lat


async def ask(messages):
    url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/v1/chat/completions"
    payload = {"model": settings.RAG_CHAT_MODEL, "messages": messages, "stream": False}
    async with httpx.AsyncClient(timeout=300) as c:
        r = await c.post(url, json=payload)
        return r.json()["choices"][0]["message"]["content"]


async def main():
    db = SessionLocal()
    try:
        ranked = await R.retrieve(db, Q)
        ctx = R.build_context_block(ranked)
        base = R.GUIDE_SYSTEM_PROMPT.format(context=ctx)
        # ZH: 語言指令本身四種擺法都用同一段文字，只有位置不同。
        d = R.language_directive(Q)

        variants = {
            "A 附加在 system 最後":   [{"role": "system", "content": base + d}],
            "B 插在 system 最前面":   [{"role": "system", "content": d + "\n\n" + base}],
            "C 獨立 system 放最後":   [{"role": "system", "content": base},
                                       {"role": "system", "content": d}],
            "D 併進使用者提問":       [{"role": "system", "content": base}],
        }
        for name, head in variants.items():
            for n in range(REPEATS):
                user = Q if name[0] != "D" else Q + "\n\n" + d
                out = await ask(head + [{"role": "user", "content": user}])
                han, lat = cjk_ratio(out)
                verdict = "英文 O" if lat > han else "中文 X"
                print(f"  {name:<22} 第{n+1}次  漢字{han:4} 拉丁{lat:4}  {verdict}")
                print(f"       {out.strip()[:90].replace(chr(10),' ')}")
    finally:
        db.close()

asyncio.run(main())
