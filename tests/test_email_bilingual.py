"""
ZH: 每一封寄出去的信都必須同時有中文與英文（主旨與內文都要）。

ZH: 🔴 為什麼要用測試守：這是**新增信件時最容易漏掉的一件事**,
    而且漏了不會有任何錯誤 —— 信照樣寄得出去,只是收件人看不懂。

ZH: 這裡不掃原始碼字串,而是**真的呼叫每個 send_* 並攔截送出的內容**。
    掃原始碼會出兩種錯:主旨常常是變數組出來的（首次/最後通知兩種版本各寫各的）,
    而且 `html = f\"\"\"...\"\"\"` 的內文會被當成 docstring 一起剝掉 ——
    量到的其實只有主旨,信裡少了半種語言也照樣綠燈。

ZH: 新增 send_* 函式時,若沒有加進 CASES,test_every_sender_is_covered 會失敗 ——
    刻意如此:漏測跟漏翻譯一樣看不出來。
"""
import inspect
import re

import pytest

from app.services import email_service


# ZH: 中文 = CJK 統一表意文字。內文的英文 = 連續三個以上的英文詞
#     （單獨的 "MYAI"、"IP" 這種縮寫不算翻譯）。
_ZH = re.compile(r"[\u4e00-\u9fff]")
_EN = re.compile(r"\b[A-Za-z]{2,}\b(\s+\b[A-Za-z]{2,}\b){2,}")


def assert_bilingual_subject(subject: str, who: str) -> None:
    """
    ZH: 主旨的雙語檢查 —— 檢查的是**慣例**（`中文 | English`）,不是「有沒有英文字母」。

    ZH: 🔴 為什麼不沿用內文那條「連續三個英文詞」的規則：
        主旨天生就短,「Test alert」只有兩個詞就會被判成沒英文。
        而把門檻降到兩個詞,「AI Base」這種產品名又會讓純中文主旨蒙混過關 ——
        兩種錯法都會讓這個測試變成裝飾品。
        改成檢查分隔線後面那段是純英文,兩種錯法都躲不掉。

    @node tests/test_email_bilingual.py::assert_bilingual_subject
    """
    assert "|" in subject, f"{who} 主旨沒有用「中文 | English」的雙語格式: {subject!r}"
    tail = subject.rsplit("|", 1)[1].strip().rstrip("]").strip()
    assert tail, f"{who} 主旨分隔線後面是空的: {subject!r}"
    assert not _ZH.search(tail), f"{who} 主旨的英文段裡混了中文: {tail!r}"
    assert re.search(r"[A-Za-z]{2,}", tail), f"{who} 主旨缺英文: {subject!r}"
    assert _ZH.search(subject), f"{who} 主旨缺中文: {subject!r}"


# ZH: (函式名, 位置參數) —— 有多種變體的信要每種都測,
#     因為變體常常是各寫各的主旨（見 send_temp_password 的開通/重設）。
CASES = [
    ("send_login_alert",           ("u@example.com", "小明", "1.2.3.4")),
    ("send_password_change_alert", ("u@example.com", "小明")),
    ("send_temp_password",         ("u@example.com", "小明", "pw1234", True)),
    ("send_temp_password",         ("u@example.com", "小明", "pw1234", False)),
    ("send_myai_provisioned",      ("u@example.com", "小明", "https://ai.example.com")),
    ("send_lab_purge_reminder",    ("u@example.com", "小明", 7, "2026-09-10", "first")),
    ("send_lab_purge_reminder",    ("u@example.com", "小明", 1, "2026-09-10", "final")),
    ("send_myai_balance_alert",    ("u@example.com", "小明", "uid-1", "low", 120, 500, "https://g")),
    ("send_myai_balance_alert",    ("u@example.com", "小明", "uid-1", "empty", 0, 500, "")),
]


@pytest.fixture
def sent(monkeypatch):
    """ZH: 攔截 send_email,拿到真正要寄出去的 (主旨, 內文)。不碰 SMTP、不寫 DB。"""
    box = []
    monkeypatch.setattr(email_service, "send_email",
                        lambda to, subject, html, **kw: box.append((subject, html)))
    return box


@pytest.mark.parametrize("fn_name,args", CASES,
                         ids=[f"{n}-{i}" for i, (n, _) in enumerate(CASES)])
def test_subject_and_body_are_bilingual(sent, fn_name, args):
    getattr(email_service, fn_name)(*args)
    assert len(sent) == 1, f"{fn_name} 沒有呼叫 send_email"
    subject, html = sent[0]

    assert_bilingual_subject(subject, fn_name)
    assert _ZH.search(html), f"{fn_name} 內文缺中文"
    assert _EN.search(html), f"{fn_name} 內文缺英文"


def test_every_sender_is_covered():
    """ZH: 新增一封信卻沒加進 CASES → 這裡失敗。漏測跟漏翻譯一樣看不出來。"""
    senders = {
        name for name, obj in vars(email_service).items()
        if name.startswith("send_") and inspect.isfunction(obj)
        # ZH: send_email 是底層送信,沒有自己的文案;
        #     send_admin_alert 的主旨與內文都由呼叫端傳入,在下面兩個測試守。
        and name not in ("send_email", "send_admin_alert")
    }
    missing = senders - {n for n, _ in CASES}
    assert not missing, f"這些信沒有雙語測試: {sorted(missing)}"


def test_admin_alert_body_is_bilingual(monkeypatch):
    """
    ZH: 管理員告警的內文由 scheduler._alert 組出來（send_admin_alert 只負責轉手,
        主旨與內文都是呼叫端給的）—— 所以守在 _alert 這一層。
    """
    from app import scheduler

    box = []
    # ZH: _alert 是在函式內才 `from .services import email_service`,
    #     所以要換掉來源模組的屬性 —— 那句 import 執行時會拿到換過的版本。
    monkeypatch.setattr(email_service, "send_admin_alert",
                        lambda kind, subject, html: box.append((subject, html)) or 1)
    scheduler._alert("unit_test", "測試告警 | Test alert", "boom")

    assert len(box) == 1, "_alert 沒有把告警交給 send_admin_alert"
    subject, html = box[0]
    assert_bilingual_subject(subject, "管理員告警")
    assert _ZH.search(html), "告警內文缺中文"
    assert _EN.search(html), "告警內文缺英文"


def test_scheduler_alert_titles_are_bilingual():
    """
    ZH: 告警主旨＝呼叫端給的 title,所以守在呼叫端。
        讀原始碼是刻意的 —— 這些 _alert() 都在 except 區塊裡,
        要觸發它們得先讓背景迴圈真的壞掉,測試裡造不出來。
    """
    import pathlib

    src = pathlib.Path(email_service.__file__).parent.parent / "scheduler.py"
    titles = re.findall(r'_alert\(\s*"[^"]+"\s*,\s*"([^"]+)"', src.read_text(encoding="utf-8"))
    assert titles, "找不到任何 _alert() 呼叫 —— 樣式改了就要更新這個測試"
    for t in titles:
        assert_bilingual_subject(t, "告警標題")
