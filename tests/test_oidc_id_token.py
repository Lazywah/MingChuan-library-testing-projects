# -*- coding: utf-8 -*-
"""
ZH: OIDC id_token 的簽章驗證（v4.24）。

ZH: 🔴 **身分不是從 id_token 來的**（MCU 的 userinfo 才是，見 sso_client 檔頭）。
    這一層是縱深防禦，擋的是兩件事：
      · token endpoint 回的 token 其實屬於別人（token substitution）
      · 這次的 token 是別次登入的重播（nonce 不對）

ZH: 🔴 這一族最重要的兩條在 `TestAlgorithmConfusion`：
    auth.mcu.edu.tw 的 discovery **自己宣告支援 `none` 與 HS256**。
    照單全收的話：
      · alg=none  → 完全不必簽章
      · alg=HS256 → 拿**公鑰**當 HMAC 密鑰（公鑰是公開的，誰都簽得出來）
    兩種都是經典手法，而且驗證「看起來有在跑」——所以一定要有測試釘住。

@node tests/test_oidc_id_token.py
"""
import time

import pytest
from jose import jwt as jose_jwt

from app.sso_client import OIDCSSOClient

ISSUER = "https://idp.example.edu"
CLIENT_ID = "client-abc"

# ZH: 測試用的 RSA 金鑰對（2048 bit，只在測試裡用）。
#     產生方式：cryptography 的 rsa.generate_private_key —— 這裡直接在 fixture 生，
#     不寫死一把在原始碼裡（寫死的金鑰遲早會被複製到別的地方用）。


@pytest.fixture(scope="module")
def keypair():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from jose import jwk as jose_jwk

    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    pub_pem = priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    jwk_pub = jose_jwk.construct(pub_pem, "RS256").to_dict()
    jwk_pub = {k: (v.decode() if isinstance(v, bytes) else v) for k, v in jwk_pub.items()}
    jwk_pub["kid"] = "test-key-1"
    return {"private_pem": pem, "public_pem": pub_pem, "jwk": jwk_pub}


@pytest.fixture
def client(keypair, monkeypatch):
    """ZH: 一個不會真的連網的 OIDC client（discovery 與 jwks 都餵假的）。"""
    c = OIDCSSOClient(discovery_url="https://idp.example.edu/.well-known/openid-configuration",
                      client_id=CLIENT_ID, client_secret="s3cret",
                      redirect_uri="https://ai.example.edu/cb")
    monkeypatch.setattr(c, "_endpoints", lambda: {
        "issuer": ISSUER,
        "authorization_endpoint": ISSUER + "/authorize",
        "token_endpoint": ISSUER + "/token",
        "userinfo_endpoint": ISSUER + "/userinfo",
        "jwks_uri": ISSUER + "/jwks",
    })
    c._jwks_keys = {keypair["jwk"]["kid"]: keypair["jwk"]}
    c._jwks_at = time.time()
    return c


def _b64u(b: bytes) -> str:
    """@node tests/test_oidc_id_token.py::_b64u"""
    import base64
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _forge(keypair, alg, sig_key=None, **claims):
    """
    ZH: **手工**組一個 token —— 攻擊者就是這樣做的。

    ZH: 🔴 為什麼不用 jose 來簽：python-jose **拒絕**產生 alg=none，
        也拒絕拿公鑰當 HMAC 密鑰。用它來造攻擊樣本會在「造」的那一步就失敗，
        於是測試變成在驗證 jose 的自我保護，而不是驗證**我們的**檢查。
        我們不能假設所有客戶端都這麼有良心 —— 攻擊者用的是 curl。

    @node tests/test_oidc_id_token.py::_forge
    """
    import hashlib
    import hmac as _hmac
    import json

    body = {"iss": ISSUER, "aud": CLIENT_ID, "sub": "12345678",
            "iat": int(time.time()), "exp": int(time.time()) + 300}
    body.update(claims)
    header = {"alg": alg, "typ": "JWT", "kid": keypair["jwk"]["kid"]}
    signing_input = (_b64u(json.dumps(header).encode())
                     + "." + _b64u(json.dumps(body).encode()))
    if alg == "none":
        return signing_input + "."
    sig = _hmac.new(sig_key.encode(), signing_input.encode(), hashlib.sha256).digest()
    return signing_input + "." + _b64u(sig)


def _token(keypair, alg="RS256", key=None, **claims):
    """ZH: 簽一個 id_token。預設是「完全正確」的那一個，測試各自改壞一項。

    @node tests/test_oidc_id_token.py::_token
    """
    body = {
        "iss": ISSUER, "aud": CLIENT_ID, "sub": "12345678",
        "iat": int(time.time()), "exp": int(time.time()) + 300,
    }
    body.update(claims)
    signing_key = key if key is not None else keypair["private_pem"]
    return jose_jwt.encode(body, signing_key, algorithm=alg,
                           headers={"kid": keypair["jwk"]["kid"]})


# ── 正常情況 ────────────────────────────────────────────────────────────
def test_a_good_token_passes(client, keypair):
    claims = client._verify_id_token(_token(keypair), expected_nonce=None,
                                     expected_sub="12345678")
    assert claims["sub"] == "12345678"


# ── 演算法混淆 ──────────────────────────────────────────────────────────
class TestAlgorithmConfusion:
    def test_alg_none_is_refused(self, client, keypair):
        """ZH: 🔴 alg=none ＝ 不必簽章。IdP 的 discovery 真的宣告支援它。"""
        unsigned = _forge(keypair, "none")
        with pytest.raises(ValueError) as e:
            client._verify_id_token(unsigned, None, "12345678")
        assert "演算法" in str(e.value)

    def test_hs256_signed_with_the_public_key_is_refused(self, client, keypair):
        """
        ZH: 🔴 經典手法：公鑰是**公開**的，攻擊者拿它當 HMAC 密鑰簽一個 HS256，
            而只看「簽章驗得過」的實作會通過。釘死 RS* 才擋得掉。
        """
        forged = _forge(keypair, "HS256", sig_key=keypair["public_pem"], sub="99999999")
        with pytest.raises(ValueError):
            client._verify_id_token(forged, None, "99999999")


# ── 簽章與 claim ────────────────────────────────────────────────────────
class TestClaims:
    def test_a_token_signed_by_someone_else_is_refused(self, client, keypair):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        other_pem = other.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()).decode()
        with pytest.raises(ValueError):
            client._verify_id_token(_token(keypair, key=other_pem), None, "12345678")

    def test_wrong_audience_is_refused(self, client, keypair):
        """ZH: aud 是別人的 client_id ＝ 這個 token 不是發給我們的。"""
        with pytest.raises(ValueError):
            client._verify_id_token(_token(keypair, aud="someone-else"), None, "12345678")

    def test_wrong_issuer_is_refused(self, client, keypair):
        with pytest.raises(ValueError):
            client._verify_id_token(_token(keypair, iss="https://evil.example"),
                                    None, "12345678")

    def test_expired_is_refused(self, client, keypair):
        """ZH: ⚠ 過期要超過容忍值才算過期（見下一條）——所以這裡用 10 分鐘前。"""
        with pytest.raises(ValueError):
            client._verify_id_token(_token(keypair, exp=int(time.time()) - 600),
                                    None, "12345678")

    def test_a_few_seconds_of_clock_skew_is_tolerated(self, client, keypair):
        """
        ZH: 🔴 **刻意**容忍 60 秒的時鐘誤差。兩邊的時鐘不會完全一致，
            而差幾秒就把人擋在門外的症狀是「有時候登得進去有時候不行」——
            那是最難查的一種。這條把「容忍」釘成規格，
            免得下一個人看到 `leeway` 以為是忘了拿掉的除錯碼。
        """
        claims = client._verify_id_token(_token(keypair, exp=int(time.time()) - 10),
                                         None, "12345678")
        assert claims["sub"] == "12345678"

    def test_unknown_kid_is_refused(self, client, keypair, monkeypatch):
        """ZH: 沒看過的 kid 會重抓 jwks；還是找不到就拒絕（不是放行）。"""
        monkeypatch.setattr(client, "_jwks", lambda force=False: {"other-kid": keypair["jwk"]})
        with pytest.raises(ValueError) as e:
            client._verify_id_token(_token(keypair), None, "12345678")
        assert "kid" in str(e.value)


# ── 對帳：nonce 與 sub ──────────────────────────────────────────────────
class TestBinding:
    def test_nonce_must_match(self, client, keypair):
        """ZH: 🔴 nonce 綁定「這一次的登入請求」—— 擋別次登入結果的重播。"""
        tok = _token(keypair, nonce="the-right-one")
        assert client._verify_id_token(tok, "the-right-one", "12345678")
        with pytest.raises(ValueError) as e:
            client._verify_id_token(tok, "a-different-one", "12345678")
        assert "nonce" in str(e.value)

    def test_sub_must_match_userinfo(self, client, keypair):
        """ZH: 🔴 id_token 說的人必須就是 userinfo 回的那個人。
           不一致＝拿到別人的 token，這是最該擋下來的情況。"""
        with pytest.raises(ValueError) as e:
            client._verify_id_token(_token(keypair, sub="11111111"), None, "22222222")
        assert "不同的使用者" in str(e.value)


# ── nonce 是怎麼來的 ────────────────────────────────────────────────────
class TestNonceDerivation:
    def test_the_same_state_always_gives_the_same_nonce(self, client):
        """ZH: 登入時與 callback 時要算得出同一個值（平台沒有 session 儲存區）。"""
        st = client._sign_state()
        assert client.nonce_for_state(st) == client.nonce_for_state(st)
        assert len(client.nonce_for_state(st)) == 32

    def test_different_states_give_different_nonces(self, client):
        a, b = client._sign_state(), client._sign_state()
        assert client.nonce_for_state(a) != client.nonce_for_state(b)

    def test_the_nonce_is_not_the_state_itself(self, client):
        """
        ZH: 🔴 state 會出現在**網址列與 Referer**。直接拿它當 nonce 的話，
            看得到網址的人就拿到了 nonce —— 那等於沒有 nonce。
        """
        st = client._sign_state()
        n = client.nonce_for_state(st)
        assert n not in st and st not in n

    def test_a_broken_state_gives_an_empty_nonce(self, client):
        """ZH: 算不出來就回空字串（呼叫端當成「這次不驗 nonce」）——
           state 本身已經先被 verify_state 擋掉了。"""
        assert client.nonce_for_state("not-base64!!") == ""

    def test_the_login_url_carries_the_nonce(self, client):
        import urllib.parse as up
        q = up.parse_qs(up.urlparse(client.get_login_url()).query)
        assert q["nonce"][0] == client.nonce_for_state(q["state"][0])
