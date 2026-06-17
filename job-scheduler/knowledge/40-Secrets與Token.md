# Secrets 管理與 Token 用量

## Secrets（API 金鑰）管理

如果你的程式需要呼叫付費 API（例如 OpenAI、Claude、HuggingFace），可在「Compute Tasks」→「Notebook」分頁下方的「**Secrets 管理**」新增金鑰。

### 如何新增 Secret

1. 在「Secrets 管理」區塊輸入：
   - **名稱**：環境變數名稱，例如 `HF_TOKEN`、`OPENAI_API_KEY`、`WANDB_API_KEY`。
   - **值**：你的金鑰（會以 AES-256-GCM 加密儲存）。
2. 按「新增」。

### 如何在程式中使用

啟動 Lab 或提交 GPU 任務時，這些 secret 會自動以「環境變數」注入容器。程式裡用：

```python
import os
key = os.environ["HF_TOKEN"]
```

### 我需要設定 Secret 嗎？

只有要呼叫 OpenAI / Claude / HuggingFace 等需要金鑰的付費 API 才需要。一般 Python 作業或學習用途可以略過。金鑰絕不會被寫進程式碼或外洩，僅在執行時解密注入。

## Token 用量與配額

平台對 AI 對話／生成類功能有 Token 配額（預設每月上限數百萬 Token）。

- **查看用量**：在「Settings（系統設定）」分頁可看到 Token Usage（已用 / 上限）與用量環圖。
- **配額重置**：每月會重置一次。
- **用量超過上限**：使用 AI 對話時若顯示「Token quota exceeded（額度已用盡）」，代表本月配額用完，需等待下次重置或聯絡管理員調整額度。

> 注意：右下角的「客服助手」（平台導覽問答）不計入你的 Token 配額，可放心使用。
