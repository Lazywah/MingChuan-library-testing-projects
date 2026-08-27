import smtplib
import logging
from email.utils import make_msgid
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
from ..config import settings

logger = logging.getLogger(__name__)

def _record(to_email: str, subject: str, status: str, detail: str = None,
            kind: str = None, username: str = None, user_id: str = None,
            message_id: str = None) -> None:
    """
    ZH: 寫一筆寄信紀錄（自行開 session —— 本模組多由 BackgroundTasks 呼叫，沒有現成 db）。
        記錄失敗絕不影響寄信流程本身。
    EN: Persist one outbound-email record; never let logging break the send path.

    @node job-scheduler/app/services/email_service.py::_record
    """
    try:
        from ..database import SessionLocal
        from .. import models
        db = SessionLocal()
        try:
            db.add(models.EmailLog(
                to_email=to_email, subject=subject, status=status,
                detail=(detail or None), kind=kind, username=username, user_id=user_id,
                message_id=(message_id or None),
            ))
            db.commit()
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"寫入寄信紀錄失敗（不影響寄信）: {e}")


# ZH: RFC 2606 / RFC 6761 保留給「文件與測試」的網域與 TLD。
#     這些**規範上就不可投遞**，寄過去必定退信到我們的寄件信箱。
#     這不是對可投遞性的猜測，是規範定義的事實，所以可以硬擋。
# EN: RFC 2606 / 6761 reserved names — undeliverable by definition, never send.
#     `localhost` 要單獨列：它是 TLD 本身，不以 `.localhost` 結尾。
_RESERVED_DOMAINS = {"example.com", "example.net", "example.org", "example.edu",
                     "localhost", "test", "invalid", "example"}
_RESERVED_TLDS = (".test", ".example", ".invalid", ".localhost")


def is_undeliverable_by_spec(to_email: str) -> bool:
    """ZH: 收件網域是否為規範保留（必定退信）。

    @node job-scheduler/app/services/email_service.py::is_undeliverable_by_spec
    """
    dom = (to_email or "").rsplit("@", 1)[-1].strip().lower()
    return dom in _RESERVED_DOMAINS or dom.endswith(_RESERVED_TLDS)


def _smtp():
    """
    ZH: 取 SMTP 生效設定（管理端覆寫優先，否則 `.env`）。本模組多由 BackgroundTasks
        呼叫、手上沒有 db，所以自行開一個 session。

    ZH: **讀設定失敗一律回退純 `.env`，絕不讓寄信路徑因為讀不到設定而中斷。**
        這裡不寫 email log —— 這個函式在 send_email 決定要不要寄之前就跑，
        還不知道該記哪一封。

    @node job-scheduler/app/services/email_service.py::_smtp
    """
    try:
        from ..database import SessionLocal
        from .. import crud
        db = SessionLocal()
        try:
            return crud.effective_smtp(db)
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001
        logger.warning("讀取 SMTP 設定失敗，回退 .env：%s", e)
        return {"server": settings.SMTP_SERVER, "port": settings.SMTP_PORT,
                "username": settings.SMTP_USERNAME, "from_email": settings.SMTP_FROM_EMAIL,
                "password": settings.SMTP_PASSWORD}


def send_email(to_email: str, subject: str, html_content: str,
               kind: str = None, username: str = None, user_id: str = None):
    """
    ZH: 寄送電子郵件的核心方法。

        ⚠️ **「成功」的真正含意**：`sendmail()` 不拋錯只代表**中繼伺服器收下了**，
        **不代表已送達**。網域存在但信箱不存在（例如我們替教職員合成的
        `員編@me.mcu.edu.tw`）會被中繼接受，稍後才**非同步退信到寄件人信箱**——
        那封退信不會回到程式裡。故此處狀態記為 `sent`（已交付 SMTP），不宣稱送達。

        能明確捕捉的失敗：
          refused — 收件人在 SMTP 交談當下就被拒（`SMTPRecipientsRefused` 或
                    `sendmail()` 回傳的被拒清單）
          failed  — 連線 / TLS / 認證 / 其他例外
          mock    — 未設定 SMTP_SERVER，只印 log 不實際寄出
    EN: Core send. `sent` = accepted by relay, NOT delivered (async bounces are
        invisible to us). Captures refused recipients and hard failures.

    @node job-scheduler/app/services/email_service.py::send_email
    """
    # ZH: v3.5 自己產 Message-ID —— 退信(DSN)會夾帶原信的 Message-ID，這是把
    #     「非同步退信」對回「當初那一封」的唯一可靠鍵。交給 SMTP 伺服器自動產的話
    #     我們拿不到值，之後只能靠 to_email 猜，同一人寄過多封就會對錯。
    cfg = _smtp()
    msg_id = make_msgid(domain=((cfg["from_email"] or "").split("@")[-1] or None))

    # ZH: 保留網域一律不寄。這道閘門刻意放在**最前面、且不依賴任何設定** ——
    #     實測踩過：跑測試時 conftest 沒有覆蓋 SMTP_SERVER，43 個測試登入點
    #     真的往 xxx@example.com 寄了信，全數退回寄件信箱（2026-08-15，約 35 封）。
    #     測試端的防線（設定 SMTP_SERVER="" 走 mock）有效，但那是**外部**防線，
    #     改壞了就破功；這一道在寄信路徑內，任何呼叫端都繞不過去。
    if is_undeliverable_by_spec(to_email):
        logger.warning("拒寄：%s 是 RFC 2606/6761 保留網域，規範上不可投遞", to_email)
        _record(to_email, subject, "blocked", "reserved domain (RFC 2606/6761)",
                kind, username, user_id, msg_id)
        return

    if not cfg["server"]:
        logger.info(f"========== [MOCK EMAIL] ==========")
        logger.info(f"To: {to_email}")
        logger.info(f"Subject: {subject}")
        logger.info(f"Content: \n{html_content}")
        logger.info(f"==================================")
        _record(to_email, subject, "mock", "SMTP 主機未設定，未實際寄出",
                kind, username, user_id, msg_id)
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = cfg["from_email"]
        msg["To"] = to_email
        msg["Message-ID"] = msg_id

        part = MIMEText(html_content, "html")
        msg.attach(part)

        server = smtplib.SMTP(cfg["server"], cfg["port"])
        try:
            server.ehlo()
            server.starttls()
            if cfg["username"] and cfg["password"]:
                server.login(cfg["username"], cfg["password"])

            # ZH: sendmail 回傳 dict = 「部分收件人被拒」（其餘仍送出）；原本這個回傳值被丟掉
            refused = server.sendmail(cfg["from_email"], to_email, msg.as_string())
        finally:
            try:
                server.quit()
            except Exception:  # noqa: BLE001 - 關閉失敗不影響已送出的信
                pass

        if refused:
            logger.warning(f"收件人被拒 {to_email}: {refused}")
            _record(to_email, subject, "refused", str(refused)[:400], kind, username, user_id, msg_id)
        else:
            # ZH: 措辭刻意不用「successfully sent」——那會讓人誤以為已送達
            logger.info(f"已交付 SMTP 伺服器（不代表已送達）: {to_email}")
            _record(to_email, subject, "sent", None, kind, username, user_id, msg_id)

    except smtplib.SMTPRecipientsRefused as e:
        logger.warning(f"收件人全部被拒 {to_email}: {e.recipients}")
        _record(to_email, subject, "refused", str(e.recipients)[:400], kind, username, user_id, msg_id)
    except Exception as e:
        logger.error(f"寄信失敗 {to_email}: {e}")
        _record(to_email, subject, "failed", str(e)[:400], kind, username, user_id, msg_id)

ALERT_KIND_PREFIX = "alert:"


def _alert_recent(db, kind: str, hours: int) -> bool:
    """ZH: 這一類告警在 `hours` 小時內已經寄過了嗎。

    ZH: 用 email_log 當節流狀態,不另外開一張表 —— 「上次寄的時間」本來就記在那裡,
        另存一份就會有兩個真相。

    @node job-scheduler/app/services/email_service.py::_alert_recent
    """
    from .. import models
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    row = (db.query(models.EmailLog)
           .filter(models.EmailLog.kind == ALERT_KIND_PREFIX + kind)
           .order_by(models.EmailLog.created_at.desc())
           .first())
    if row is None or row.created_at is None:
        return False
    # ZH: created_at 存進去時是 aware(UTC),但 SQLite 讀回來是 naive ——
    #     直接跟 aware 的 since 相比會 TypeError,而這個函式一旦拋錯,
    #     節流就等於失效、告警會變成每輪一封。所以在這裡補上時區。
    last = row.created_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return last > since


def send_admin_alert(kind: str, subject: str, html_content: str) -> int:
    """
    ZH: 寄一封**管理員告警信**給設定裡的收件人清單。

    ZH: 回傳值是**交給 send_email 的封數,不是送達數,也不是「有寄出去」**。
        保留網域會在 send_email 裡被擋下(記成 blocked)、中繼拒收會記成 refused,
        兩種都算在回傳值裡。沿用本模組一貫的措辭:我們只宣稱做到哪一步。
        收件人全部填錯的話,告警會**安靜地被擋掉而且照樣計入節流** ——
        要確認告警真的出得去,看寄信紀錄頁的 alert:* 那幾筆狀態。

    ZH: 三個刻意的設計：

        1. **收件人留空就完全不寄**（預設就是空的）。沒有人填收件人的告警系統
           應該安靜,而不是往某個預設信箱亂寄。

        2. **逐一寄,不用 CC/BCC。** 一個地址被拒不會連累其他人,
           而且收件人彼此看不到對方的信箱。代價是 n 封信,但告警本來就該很少。

        3. 🔴 **同一類告警有最短間隔。** 這是整件事的成敗關鍵 ——
           觸發點都在**每幾分鐘跑一次的背景迴圈**裡,壞掉的東西會一直壞著。
           沒有節流的話,一次故障就是每輪一封信,收件人第二天就會把規則設成
           全部丟垃圾桶,於是下一次真的出事時**沒有人會看到**。
           節流狀態記在 email_log 的 kind 上(`alert:<kind>`)。

    ZH: 這個函式**絕不拋錯** —— 呼叫端都在背景迴圈的 except 區塊裡,
        在那裡再炸一次會把整個迴圈打斷。

    @node job-scheduler/app/services/email_service.py::send_admin_alert
    """
    try:
        from ..database import SessionLocal
        from .. import crud
        db = SessionLocal()
        try:
            raw = crud.get_setting(db, "admin_alert_emails") or ""
            recipients = [x.strip() for x in raw.split(",") if x.strip()]
            if not recipients:
                return 0
            hours = crud.get_setting(db, "admin_alert_min_hours")
            if _alert_recent(db, kind, hours):
                logger.info("告警 %s 在 %s 小時內已寄過,這次略過", kind, hours)
                return 0
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001
        logger.warning("讀取告警設定失敗,不寄告警：%s", e)
        return 0

    sent = 0
    for addr in recipients:
        try:
            send_email(addr, subject, html_content, kind=ALERT_KIND_PREFIX + kind)
            sent += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("告警信寄給 %s 失敗：%s", addr, e)
    return sent


def send_login_alert(to_email: str, username: str, ip_address: str):
    """
    ZH: 寄送登入通知
    EN: Send login alert

    @node job-scheduler/app/services/email_service.py::send_login_alert
    """
    subject = "AI Platform - New Login Alert"
    time_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    html = f"""
    <html>
        <body>
            <h2>Hello {username},</h2>
            <p>We noticed a new login to your AI Platform account.</p>
            <ul>
                <li><strong>IP Address:</strong> {ip_address}</li>
                <li><strong>Time:</strong> {time_str}</li>
            </ul>
            <p>If this was you, you can ignore this message. If not, please contact your administrator immediately and change your password.</p>
            <br>
            <p>Best regards,<br>AI Platform Team</p>
        </body>
    </html>
    """
    send_email(to_email, subject, html, kind="login_alert", username=username)

def send_password_change_alert(to_email: str, username: str):
    """
    ZH: 寄送密碼變更通知
    EN: Send password change alert

    @node job-scheduler/app/services/email_service.py::send_password_change_alert
    """
    subject = "AI Platform - Password Changed Successfully"
    time_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    html = f"""
    <html>
        <body>
            <h2>Hello {username},</h2>
            <p>The password for your AI Platform account has been successfully changed.</p>
            <p><strong>Time:</strong> {time_str}</p>
            <p>If you did not make this change, please contact your administrator immediately to secure your account.</p>
            <br>
            <p>Best regards,<br>AI Platform Team</p>
        </body>
    </html>
    """
    send_email(to_email, subject, html, kind="password_change_alert", username=username)

def send_temp_password(to_email: str, username: str, temp_password: str, is_new_account: bool = False):
    """
    ZH: 寄送臨時密碼或新帳號通知
    EN: Send temporary password or new account alert

    @node job-scheduler/app/services/email_service.py::send_temp_password
    """
    subject = "AI Platform - Account Provisioned" if is_new_account else "AI Platform - Password Reset"
    html = f"""
    <html>
        <body>
            <h2>Hello {username},</h2>
            <p>{'An account has been provisioned for you' if is_new_account else 'Your password has been reset'} on the AI Platform.</p>
            <p>Your temporary password is: <strong style="font-size: 18px; color: #10b981;">{temp_password}</strong></p>
            <p>Please log in and change your password immediately in the settings panel.</p>
            <br>
            <p>Best regards,<br>AI Platform Team</p>
        </body>
    </html>
    """
    send_email(to_email, subject, html,
               kind=("account_provisioned" if is_new_account else "password_reset"),
               username=username)


LAB_PURGE_KIND_PREFIX = "lab_purge:"


def send_lab_purge_reminder(to_email: str, username: str, days_left: int,
                            expires_on: str, stage: str = "first"):
    """
    ZH: 帳號已被刪除後，Lab 資料銷毀前的提醒信。

    ZH: ⚠️ 措辭前提：**寄這封信的時候帳號已經不在了。**
        所以不能寫「請登入處理」——他登不進來。能做的只有聯絡管理員還原
        （`POST /admin/lab-archives/{volume}/restore` 是管理員專屬）。
        寫成「登入即可保留」會讓人白跑一趟，然後資料照樣被銷毀。

    ZH: 也不寫「你的帳號被停權」之類的猜測 —— 我們只知道帳號被刪了，
        不知道原因（畢業、離職、管理員手動）。信裡只陳述事實與期限。

    @node job-scheduler/app/services/email_service.py::send_lab_purge_reminder
    """
    urgent = (stage == "final")
    zh_head = "【最後通知】" if urgent else ""
    en_head = "[Final notice] " if urgent else ""
    html = f"""
    <html>
        <body>
            <h2>{username} 你好 / Hello {username},</h2>
            <p>{zh_head}你在 MCU AI Base 的帳號已被移除，程式實驗室（Code Lab）的檔案
               目前<b>仍然保留著</b>，但會在 <b>{expires_on}</b>（約 {days_left} 天後）自動銷毀，
               屆時無法復原。</p>
            <p>如果還需要這些檔案，請在期限前<b>聯絡管理員</b>，由管理員還原到指定帳號。
               帳號已經移除，所以無法自行登入取回。</p>
            <hr>
            <p>{en_head}Your MCU AI Base account has been removed. Your Code Lab files are
               <b>still kept</b>, but will be destroyed on <b>{expires_on}</b>
               (in about {days_left} days) and cannot be recovered afterwards.</p>
            <p>If you still need them, <b>contact an administrator</b> before that date —
               they can restore the files to an account for you. You cannot sign in
               yourself, because the account no longer exists.</p>
            <br>
            <p>MCU AI Base</p>
        </body>
    </html>
    """
    send_email(to_email,
               f"{zh_head}程式實驗室檔案將於 {expires_on} 銷毀 / "
               f"{en_head}Code Lab files will be deleted on {expires_on}",
               html, kind=LAB_PURGE_KIND_PREFIX + stage, username=username)


def send_myai_provisioned(to_email: str, username: str, platform_url: str = ""):
    """
    ZH: v3.5 MYAI 開通完成通知。

        ⚠️ **刻意不含密碼**：初始密碼留在平台上讓本人登入後查看
        （加密存 DB、限期、可確認清除）。密碼進信箱＝多一個外洩面。

        這封信同時是**探針**：我們替 SSO 使用者組出來的信箱到底存不存在，
        只有真的寄一封才會知道 —— 寄不到會退信到我們的寄件信箱，
        由退信回收(bounce_reader)回填成 bounced。每人只寄一次。
    EN: MYAI provisioning notice. Deliberately password-free (the initial password
        stays in the platform UI). Doubles as the deliverability probe: a bounce is
        the only way to learn whether a derived address actually exists.

    @node job-scheduler/app/services/email_service.py::send_myai_provisioned
    """
    subject = "圖書館 AI 基地 - MYAI 帳號已開通 | Your MYAI account is ready"
    link = (f'<p><a href="{platform_url}">{platform_url}</a></p>' if platform_url else "")
    html = f"""
    <html>
        <body>
            <h2>{username} 你好，</h2>
            <p>你的 <strong>MYAI</strong> 帳號已自動開通，帳號即為這個信箱：
               <strong>{to_email}</strong></p>
            <p><strong>初始密碼請登入本平台查看</strong>（基於安全考量不放在信件中）。
               登入後在「AI 助手」頁面即可看到，並請盡快自行修改密碼。</p>
            {link}
            <br>
            <p>圖書館 AI 基地</p>
        </body>
    </html>
    """
    send_email(to_email, subject, html, kind="myai_provisioned", username=username)
