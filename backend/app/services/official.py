"""官方流量数据源：登录服务商客户中心抓「已用流量」

本地网卡统计和服务商的计量口径永远有偏差（方向、单位、统计层都不同），
所以这里直接抓官网的数字覆盖掉估算值——抓到就用官网的，抓不到就保持
本地统计，不阻塞面板。

密码用 SECRET_KEY 派生的 Fernet 密钥加密后存在 settings 表，接口永不回显。
"""

import asyncio
import base64
import hashlib
import logging
import os
import re
from datetime import datetime, timedelta, timezone

import httpx
from cryptography.fernet import Fernet, InvalidToken

from ..models.database import get_db
from . import traffic

logger = logging.getLogger(__name__)

TZ = timezone(timedelta(hours=8))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# 单位统一按 1024 进制换算：客户端（v2rayN 等）显示时也除以 1024，
# 两边同口径，客户端显示的数字才和官网一模一样。
UNITS = {
    "B": 1,
    "KB": 1024,
    "MB": 1024 ** 2,
    "GB": 1024 ** 3,
    "TB": 1024 ** 4,
}

KEYS = {
    "enabled": "official_enabled",
    "username": "official_username",
    "password": "official_password",
    "product_id": "official_product_id",
    "interval_min": "official_interval_min",
    "last_sync": "official_last_sync",
    "last_used": "official_last_used",
    "last_total": "official_last_total",
    "last_error": "official_last_error",
}


def _fernet() -> Fernet:
    secret = os.getenv("SECRET_KEY", "change-me-in-production").encode("utf-8")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret).digest()))


def _encrypt(text: str) -> str:
    return _fernet().encrypt(text.encode("utf-8")).decode("ascii")


def _decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, AttributeError):
        return ""


async def _get_settings(db) -> dict:
    cursor = await db.execute(
        "SELECT key, value FROM settings WHERE key IN (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        tuple(KEYS.values()),
    )
    return {row["key"]: row["value"] for row in await cursor.fetchall()}


async def _set_setting(db, key: str, value: str):
    await db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


async def get_status() -> dict:
    """给前端的状态：绝不返回明文密码"""
    async with get_db() as db:
        kv = await _get_settings(db)
    return {
        "enabled": kv.get(KEYS["enabled"]) == "1",
        "username": kv.get(KEYS["username"], ""),
        "has_password": bool(kv.get(KEYS["password"])),
        "product_id": kv.get(KEYS["product_id"], ""),
        "interval_min": int(kv.get(KEYS["interval_min"]) or 30),
        "last_sync": kv.get(KEYS["last_sync"], ""),
        "last_used": kv.get(KEYS["last_used"], ""),
        "last_total": kv.get(KEYS["last_total"], ""),
        "last_error": kv.get(KEYS["last_error"], ""),
    }


async def save_config(payload: dict) -> dict:
    async with get_db() as db:
        if "enabled" in payload:
            await _set_setting(db, KEYS["enabled"], "1" if payload["enabled"] else "0")
        if payload.get("username") is not None:
            await _set_setting(db, KEYS["username"], str(payload["username"]).strip())
        if payload.get("password"):
            await _set_setting(db, KEYS["password"], _encrypt(str(payload["password"])))
        if payload.get("product_id") is not None:
            await _set_setting(db, KEYS["product_id"], str(payload["product_id"]).strip())
        if payload.get("interval_min") is not None:
            await _set_setting(db, KEYS["interval_min"], str(int(payload["interval_min"])))
        await db.commit()
    return await get_status()


def _plain_text(html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", text)


def parse_usage(html: str):
    """从产品页里抽出 (已用字节, 总量字节, 原始片段)"""
    text = _plain_text(html)

    used = total = None

    m = re.search(r"已用流量[^\d]{0,24}([\d.]+)\s*(TB|GB|MB|KB|B)\b", text, re.I)
    if m:
        used = float(m.group(1)) * UNITS[m.group(2).upper()]

    m = re.search(r"(?:剩余流量|流量上限|总流量|套餐流量)[^\d]{0,24}([\d.]+)\s*(TB|GB|MB|KB|B)\b", text, re.I)
    if m:
        total = float(m.group(1)) * UNITS[m.group(2).upper()]

    # 回退：页面上常见的 "3.97 GB / 600.00 GB" 形式
    if used is None or total is None:
        m = re.search(r"([\d.]+)\s*(TB|GB|MB)\s*/\s*([\d.]+)\s*(TB|GB|MB)", text, re.I)
        if m:
            if used is None:
                used = float(m.group(1)) * UNITS[m.group(2).upper()]
            if total is None:
                total = float(m.group(3)) * UNITS[m.group(4).upper()]

    if used is None:
        return None, None, text[:600]

    snippet = None
    idx = text.find("已用流量")
    if idx >= 0:
        snippet = text[max(0, idx - 40): idx + 160]
    return int(used), (int(total) if total else None), snippet or text[:300]


async def fetch_usage(username: str, password: str, product_id: str) -> dict:
    """登录客户中心并抓产品页，返回 {used_bytes, total_bytes, snippet, url}"""
    async with httpx.AsyncClient(
        timeout=25, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    ) as client:
        page = await client.get("https://my.yecaoyun.com/clientarea.php")
        m = re.search(r'name="token"\s+value="([^"]+)"', page.text)
        token = m.group(1) if m else ""

        resp = await client.post(
            "https://my.yecaoyun.com/index.php?rp=/login",
            data={
                "token": token,
                "username": username,
                "password": password,
                "rememberme": "on",
                "language": "chinese",
            },
        )
        if "用户登录" in resp.text and "logout" not in resp.text.lower():
            raise RuntimeError("登录失败：账号或密码不正确，或需要验证码")

        candidates = [
            f"https://my.yecaoyun.com/clientarea.php?action=productdetails&id={product_id}",
            f"https://my.yecaoyun.com/index.php?rp=/clientarea/productdetails&id={product_id}",
            f"https://my.yecaoyun.com/index.php?rp=/clientarea/productdetails/{product_id}",
        ]
        last_snippet = ""
        for url in candidates:
            r = await client.get(url)
            if r.status_code != 200:
                continue
            used, total, snippet = parse_usage(r.text)
            last_snippet = snippet or last_snippet
            if used is not None:
                return {
                    "used_bytes": used,
                    "total_bytes": total,
                    "snippet": snippet,
                    "url": url,
                }
        raise RuntimeError(
            "已登录但没解析到流量数据，可能产品 ID 不对或页面结构有变。"
            "页面片段：" + (last_snippet[:200] if last_snippet else "(空)")
        )


async def apply_usage(used_bytes: int, total_bytes=None):
    """把官方数值写进 traffic 表（差额记下行），并同步套餐总量"""
    await traffic.snapshot()  # 确保 traffic 行存在

    async with get_db() as db:
        cursor = await db.execute("SELECT rx_used, tx_used FROM traffic WHERE id = 1")
        row = await cursor.fetchone()
        rx_used = (row["rx_used"] or 0) if row else 0
        tx_used = (row["tx_used"] or 0) if row else 0

        delta = used_bytes - (rx_used + tx_used)
        new_rx = max(0, rx_used + delta)
        await db.execute("UPDATE traffic SET rx_used = ? WHERE id = 1", (new_rx,))

        if total_bytes:
            await _set_setting(db, "quota_total_gb", f"{total_bytes / 1024 ** 3:.4f}")

        await db.commit()


async def sync_once(force: bool = False, creds: dict = None) -> dict:
    """抓一次并落库。返回执行结果（成功/失败原因）"""
    async with get_db() as db:
        kv = await _get_settings(db)

    enabled = kv.get(KEYS["enabled"]) == "1"
    if not (enabled or force or creds):
        return {"ok": False, "skipped": True, "message": "未启用"}

    username = (creds or {}).get("username") or kv.get(KEYS["username"], "")
    if (creds or {}).get("password"):
        password = creds["password"]
    else:
        password = _decrypt(kv.get(KEYS["password"], ""))
    product_id = (creds or {}).get("product_id") or kv.get(KEYS["product_id"], "")

    if not username or not password or not product_id:
        return {"ok": False, "message": "账号、密码或产品 ID 未填写完整"}

    interval = int(kv.get(KEYS["interval_min"]) or 30)
    if not force and not creds and interval > 0:
        last = kv.get(KEYS["last_sync"], "")
        if last:
            try:
                previous = datetime.fromisoformat(last)
                if datetime.now(TZ) - previous < timedelta(minutes=interval):
                    return {"ok": False, "skipped": True, "message": "未到同步间隔"}
            except ValueError:
                pass

    try:
        result = await fetch_usage(username, password, product_id)
        await apply_usage(result["used_bytes"], result["total_bytes"])

        async with get_db() as db:
            await _set_setting(db, KEYS["last_sync"], datetime.now(TZ).isoformat(timespec="seconds"))
            await _set_setting(db, KEYS["last_used"], str(result["used_bytes"]))
            await _set_setting(db, KEYS["last_total"], str(result["total_bytes"] or ""))
            await _set_setting(db, KEYS["last_error"], "")
            await db.commit()

        return {
            "ok": True,
            "used_bytes": result["used_bytes"],
            "total_bytes": result["total_bytes"],
            "snippet": result["snippet"],
            "url": result["url"],
        }
    except Exception as exc:  # noqa: BLE001
        message = f"{type(exc).__name__}: {exc}"
        logger.warning("官方流量同步失败: %s", message)
        async with get_db() as db:
            await _set_setting(db, KEYS["last_error"], message[:500])
            await db.commit()
        return {"ok": False, "message": message}


async def sync_loop():
    """后台循环：每 60 秒醒一次，到点就抓"""
    await asyncio.sleep(20)
    while True:
        try:
            await sync_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("官方流量同步循环异常: %s", exc)
        await asyncio.sleep(60)
