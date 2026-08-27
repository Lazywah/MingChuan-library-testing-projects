"""
ZH: MYAI 交易日誌的解析與「版型變了」的偵測。

ZH: 🔴 這一整套的來歷：2026-08 廠商把交易頁從 `kbx-grid` 改成 `<table>`，
    parser 一列都解不出來，但流程只印 `fetched=0` —— 讀起來就是「沒有新資料」，
    而暑假期間那完全合理。同步靜靜死了 **29 天、漏掉 201 筆**，沒有人發現。

ZH: 修法是加一個**獨立的偵測器** `tx_row_count`：只數 DOM 有幾列，
    「頁面有列卻解出 0 筆」就拋錯。
    但 2026-08-27 稽核發現那個偵測器**自己也是 `except: return 0`** ——
    HTML 解不開時它回 0、parser 回 []，於是 `seen=0, rows=[]` 不觸發錯誤，
    又變回「fetched=0，看起來像沒有新資料」。
    **偵測器跟它要偵測的東西用同一種方式壞掉，等於沒有偵測器。**

ZH: 在此之前這一整段**沒有任何測試**。
"""
import pytest

from app.services.myai_sync import (
    MyaiSyncError, parse_transactions, tx_row_count,
)


# ── 兩種版型 ──────────────────────────────────────────────────────────
V2_TABLE = """
<html><body><table><tbody>
  <tr><td>2026-08-16<br>10:23:45</td><td>-120</td><td>2033236</td>
      <td>gpt-4o 對話</td><td>a@mcu.edu.tw</td><td>1.2.3.4</td></tr>
  <tr><td>2026-08-16<br>11:00:00</td><td>-80</td><td>2033156</td>
      <td>gpt-4o 對話</td><td>a@mcu.edu.tw</td><td>1.2.3.4</td></tr>
</tbody></table></body></html>
"""

# ZH: v1 的結構比想像中深：kbx-row > kbx-grid > (kbx-time + 多個 kbx-cell kbx-dt)。
#     我第一版測試資料寫成扁平的 kbx-grid，結果解出 0 筆 ——
#     差一點就把「測試資料寫錯」誤判成「fallback parser 壞了」。
V1_KBX = """
<html><body>
  <div class="kbx-row">
    <div class="kbx-grid">
      <div class="kbx-time">2026-08-01 09:00:00</div>
      <div class="kbx-cell kbx-dt">-50</div>
      <div class="kbx-cell kbx-dt">100</div>
      <div class="kbx-cell kbx-dt">舊版型對話</div>
      <div class="kbx-cell kbx-dt">
        <div>a@mcu.edu.tw</div>
        <div class="kbx-muted">NyaLazy・sn:1003387</div>
      </div>
      <div class="kbx-cell kbx-dt">1.2.3.4</div>
    </div>
  </div>
</body></html>
"""

# ZH: 合法但真的沒有資料的頁面 —— 這種**不可以**拋錯（陽性對照的反面）
EMPTY_BUT_VALID = "<html><body><table><tbody></tbody></table></body></html>"

# ZH: 有列、但每一列的結構都不認得 —— 這就是「版型又改了」
ROWS_BUT_UNPARSEABLE = """
<html><body><table><tbody>
  <tr><td colspan="6">系統維護中，請稍後再試</td></tr>
  <tr><td colspan="6">系統維護中，請稍後再試</td></tr>
</tbody></table></body></html>
"""


def test_counts_rows_in_both_layouts():
    """ZH: 偵測器要能數兩種版型 —— 只認新版的話，回退到舊版就偵測不到。"""
    assert tx_row_count(V2_TABLE) == 2
    assert tx_row_count(V1_KBX) == 1
    assert tx_row_count(EMPTY_BUT_VALID) == 0


def test_parses_the_v2_table_layout():
    rows = parse_transactions(V2_TABLE)
    assert len(rows) == 2, rows
    # ZH: 時間欄是 `<td>2026-08-16<br>10:23:45</td>`，直接取文字會黏成
    #     `2026-08-1610:23:45` —— 這裡確認有處理掉。
    assert "2026-08-16" in str(rows[0]) and "10:23:45" in str(rows[0])


def test_parses_the_v1_kbx_layout():
    """ZH: 舊版型要留著 —— 廠商改版之後不保證不會改回去。"""
    rows = parse_transactions(V1_KBX)
    assert len(rows) == 1, rows


@pytest.mark.parametrize("bad", ["", "   ", None])
def test_unparseable_page_raises_instead_of_looking_empty(bad):
    """
    ZH: 🔴 稽核（2026-08-27）修的那一條。

    ZH: 頁面解不開時偵測器原本回 0，與「真的沒有資料」完全無法區分 ——
        於是同步會安靜地什麼都不做，日誌上只有 `fetched=0`。
        空回應是最實際的觸發點：session 過期被導向、gateway 打嗝、廠商回 204。
    """
    with pytest.raises(MyaiSyncError) as e:
        tx_row_count(bad)
    assert "解不開" in str(e.value)


def test_a_legitimately_empty_page_does_not_raise():
    """
    ZH: **陽性對照的反面，同樣重要。**
        上面那條若是因為「什麼都拋錯」而過，這個功能就會在每次
        真的沒有新交易時炸掉。合法但沒有資料的頁面必須安靜地回 0。
    """
    assert tx_row_count(EMPTY_BUT_VALID) == 0
    assert parse_transactions(EMPTY_BUT_VALID) == []


def test_rows_present_but_nothing_parsed_is_detectable():
    """
    ZH: 這就是 29 天事故的形狀：頁面上明明有列，卻一列都解不出來。
        偵測器要能看出差異（`seen > 0` 而 `rows == 0`），
        `sync_transactions` 才有辦法據此拋錯。
    """
    seen = tx_row_count(ROWS_BUT_UNPARSEABLE)
    rows = parse_transactions(ROWS_BUT_UNPARSEABLE)
    assert seen == 2, "偵測器沒看到那兩列"
    assert rows == [], "這些列不該被解出來"
    assert seen and not rows, "這正是 sync_transactions 用來拋錯的條件"
