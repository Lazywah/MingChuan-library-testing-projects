"""
==============================================================================
Service: Agent Dispatcher — v2.3 P1 多代理 dispatch (文件生成)
         Agent Dispatcher — v2.3 P1 multi-agent dispatch (document generation)
==============================================================================
ZH: 用途：依 ChatRequest.tool_type 選對應的「專項生成 agent」設定
    （system prompt + 觸發契約）。本輪只實作 tool_type="presentation"。

    設計：主 chat AI 與專項 agent 共用同一個 /chat/completions 端點與
    Portkey 路由（不另開 endpoint），差別只在注入的 system prompt 與
    後處理（偵測生成契約 → 呼叫 document_generator）。

EN: Purpose: Select the specialized generation agent config (system prompt +
    trigger contract) by ChatRequest.tool_type. This round only implements
    tool_type="presentation".

    Design: the main chat AI and specialized agents share the same
    /chat/completions endpoint and Portkey routing; the only difference is the
    injected system prompt and the post-processing (detect the generation
    contract → call document_generator).
==============================================================================
"""

from __future__ import annotations

# ==============================================================================
# ZH: 生成契約標記（後端據此從 AI 回覆中擷取結構化 spec）
# EN: Generation contract markers (backend extracts structured spec from reply)
# ==============================================================================
# ZH: AI 在「使用者確認後」才輸出此標記區塊，內含一段 JSON spec。
#     後端偵測到 START 後停止把後續內容串給前端（避免使用者看到原始 JSON），
#     擷取 START..END 之間的 JSON → document_generator 渲染 .pptx。
# EN: The AI only emits this block AFTER the user confirms; it wraps one JSON
#     spec. Backend stops streaming once START is seen (so the user never sees
#     raw JSON), extracts the JSON between START..END → document_generator.
PPTX_SPEC_START = "<<<PPTX_SPEC>>>"
PPTX_SPEC_END = "<<<END_PPTX_SPEC>>>"


_PRESENTATION_SYSTEM_PROMPT = f"""你是「文書簡報」AI 代理，專門協助大學生把想法做成 PowerPoint 簡報 (.pptx)。

# 互動流程（務必遵守，分兩個階段）
1. **討論階段**：先用「純文字」與使用者對話，釐清以下重點（一次問 1-2 個，不要一次轟炸）：
   - 主題與目的
   - 投影片張數（沒講就建議一個合理數字）
   - 目標聽眾（老師/同學/面試官…）
   - 語言（中文/英文）、風格（學術/輕鬆）
   釐清到足夠後，用純文字「條列出簡報大綱」請使用者確認，並明確問：「這樣可以開始生成嗎？」
2. **生成階段**：**只有在使用者明確同意（例如說「可以」「確認」「生成」「OK」）之後**，才輸出生成指令。
   輸出格式：先寫一句簡短中文確認句（例如「好的，正在為你生成簡報。」），
   緊接著在訊息「最後」附上下列標記區塊，區塊內是**單一合法 JSON**，不得有任何多餘文字或 ```：

{PPTX_SPEC_START}
{{
  "title": "簡報主標題",
  "subtitle": "副標題或作者（可省略）",
  "slides": [
    {{ "title": "投影片標題", "bullets": ["重點一", "重點二", "重點三"], "notes": "備忘稿（可省略）" }}
  ]
}}
{PPTX_SPEC_END}

# JSON 規則（嚴格遵守）
- `slides` 至少 1 張；每張 `bullets` 建議 3-5 條，每條精簡（不要整段文字）。
- 字串內不要放未跳脫的雙引號或換行；JSON 必須能被 json.loads 解析。
- 標記區塊只在「生成階段」出現；討論階段**絕對不要**輸出標記或 JSON。
- 不要把標記寫進程式碼區塊（不要用 ```）。

# 其他
- 若使用者要的是「給我 code 自己改」而非直接生成，就改用純文字提供 python-pptx 範例，不輸出標記。
"""


# ZH: tool_type → agent 設定表（本輪僅 presentation）
# EN: tool_type → agent config table (only presentation this round)
_AGENTS: dict[str, dict] = {
    "presentation": {
        "system_prompt": _PRESENTATION_SYSTEM_PROMPT,
        "spec_start": PPTX_SPEC_START,
        "spec_end": PPTX_SPEC_END,
    },
}


def is_dispatch_tool(tool_type: str | None) -> bool:
    """ZH: 此 tool_type 是否走專項生成 dispatch | EN: Whether this tool_type uses dispatch"""
    return (tool_type or "").strip() in _AGENTS


def get_agent_config(tool_type: str) -> dict:
    """ZH: 取得專項 agent 設定 | EN: Get specialized agent config"""
    return _AGENTS[(tool_type or "").strip()]


def get_system_prompt(tool_type: str) -> str:
    """ZH: 取得專項 agent 的 system prompt | EN: Get the agent's system prompt"""
    return _AGENTS[(tool_type or "").strip()]["system_prompt"]
