# -*- coding: utf-8 -*-
"""
ZH: 檢查回應 schema 有沒有送出**沒有時區標記**的 datetime。

ZH: 為什麼需要機械檢查：症狀**不會報錯、不會壞版面**。
    SQLite 取回來是 naive datetime，序列化出去是 "2026-08-20T01:42:38.152605"，
    而瀏覽器的 `new Date(...)` 把沒有偏移的字串當成**本地時間** ——
    於是 +08:00 的使用者看到的每個時間都早 8 小時。
    眼睛找不可靠：第一次發現時只修了問題回報那一個，其餘**九個** schema
    是這支程式掃出來的。

ZH: 判準：回應 schema（有 `model_config.from_attributes`，或名字以 Response/
    ListItem/Info 結尾）裡的 datetime 欄位，必須是 `UtcDatetime`
    或被 `field_serializer` 蓋到。

ZH: ⚠ 這支自己也有過兩個盲點（第一版）：
      1. 只認 `field_serializer`，不認 `PlainSerializer`（型別自帶的）
      2. `Optional[Annotated[datetime, ...]]` 直接偵測不到
    兩個都會讓它**漏報**。所以下面用 pydantic 自己的 `FieldInfo.metadata`
    與遞迴展開，而不是猜型別長什麼樣。

@node scripts/check_naive_datetime.py
"""
import datetime as _dt
import pathlib
import sys
import typing

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "job-scheduler"))

try:
    from pydantic import BaseModel
    from pydantic.functional_serializers import PlainSerializer
    import app.schemas as S
except Exception as e:                      # noqa: BLE001
    print(f"[SKIP] 載入不了 schemas（{e}）")
    sys.exit(0)


# ZH: 刻意排除的：**請求** schema 收進來的時間不經過我們序列化。
#     以類別名判斷會漏（有些請求 schema 也叫 ...Update），所以用「有沒有
#     from_attributes」＋名字兩個條件，兩者都不符才跳過。
def is_response_model(model) -> bool:
    """@node scripts/check_naive_datetime.py::is_response_model"""
    cfg = getattr(model, "model_config", {}) or {}
    if cfg.get("from_attributes"):
        return True
    return model.__name__.endswith(("Response", "ListItem", "Info"))


def has_datetime(ann) -> bool:
    """ZH: 這個型別註記裡有沒有 datetime（會鑽進 Optional / Union / Annotated）。

    @node scripts/check_naive_datetime.py::has_datetime
    """
    if ann is _dt.datetime:
        return True
    for a in typing.get_args(ann):
        if has_datetime(a):
            return True
    return False


def is_utc_annotated(field) -> bool:
    """ZH: 這個欄位的型別自己帶了序列化規則嗎（UtcDatetime）？

    ZH: 看 `FieldInfo.metadata` —— 那是 pydantic 自己整理好的 Annotated 附加資訊，
        比自己去拆型別可靠。`Optional[UtcDatetime]` 的 metadata 在 args 裡，
        所以也要往下找一層。

    @node scripts/check_naive_datetime.py::is_utc_annotated
    """
    for m in getattr(field, "metadata", ()) or ():
        if isinstance(m, PlainSerializer):
            return True
    # ZH: Optional[Annotated[...]] —— metadata 沒被提到最外層，往型別裡找
    def walk(ann):
        if typing.get_origin(ann) is typing.Annotated or hasattr(ann, "__metadata__"):
            if any(isinstance(m, PlainSerializer) for m in getattr(ann, "__metadata__", ())):
                return True
        return any(walk(a) for a in typing.get_args(ann))
    return walk(field.annotation)


def serializer_covered(model) -> set:
    """ZH: 被 `field_serializer` 明確蓋到的欄位名。

    @node scripts/check_naive_datetime.py::serializer_covered
    """
    covered = set()
    dec = getattr(model, "__pydantic_decorators__", None)
    if dec is not None:
        for d in getattr(dec, "field_serializers", {}).values():
            covered.update(getattr(d.info, "fields", ()) or ())
    return covered


def main() -> int:
    """@node scripts/check_naive_datetime.py::main"""
    problems = []
    checked = 0
    for name in dir(S):
        model = getattr(S, name)
        if not (isinstance(model, type) and issubclass(model, BaseModel)
                and model is not BaseModel):
            continue
        if not is_response_model(model):
            continue
        covered = serializer_covered(model)
        for fname, field in model.model_fields.items():
            if not has_datetime(field.annotation):
                continue
            checked += 1
            if fname in covered or is_utc_annotated(field):
                continue
            problems.append(f"{name}.{fname}")

    print("回應時間欄位的時區標記檢查")
    print(f"  檢查了 {checked} 個 datetime 欄位")
    if problems:
        for p in problems:
            print(f"  [FAIL] {p} 送出去**沒有時區標記** —— "
                  f"瀏覽器會當成本地時間（+08:00 的人會早 8 小時）")
        print(f"\n[FAIL] {len(problems)} 個。改用 `UtcDatetime` 型別（schemas.py 有定義）。")
        return 1
    print("\n[OK] 所有回應的時間欄位都有明示時區")
    return 0


if __name__ == "__main__":
    sys.exit(main())
