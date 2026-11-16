"""流量统计：按计费周期累计网卡收发字节

数据源是 /proc/net/dev —— 面板容器用 host 网络，读到的就是宿主机网卡。
网卡累计值会随重启归零，所以这里把每次读到的增量累加进数据库，
并用 period_start 区分计费周期，避免重启和跨周期算错。

套餐参数（总量、重置日/时刻）优先读数据库 settings 表，面板里可以改；
没设置时回退环境变量，再回退默认值。
"""

import os
from datetime import datetime, timedelta, timezone

from ..models.database import get_db

# 计费周期按服务商所在时区算（服务商给的重置时间是 UTC+8）
TZ = timezone(timedelta(hours=8))

# 面板字段 -> settings 表的 key
SETTING_KEYS = {
    "total_gb": "quota_total_gb",
    "reset_day": "quota_reset_day",
    "reset_time": "quota_reset_time",
}


def _parse_reset_time(raw) -> tuple:
    try:
        hh, mm = str(raw).split(":")
        hh, mm = int(hh), int(mm)
        if 0 <= hh < 24 and 0 <= mm < 60:
            return hh, mm
    except (ValueError, AttributeError):
        pass
    return 10, 31


async def load_config(db) -> dict:
    """读套餐配置：数据库优先，没配过就用环境变量"""
    cursor = await db.execute(
        "SELECT key, value FROM settings WHERE key IN (?, ?, ?)",
        tuple(SETTING_KEYS.values()),
    )
    kv = {row["key"]: row["value"] for row in await cursor.fetchall()}

    raw_total = kv.get("quota_total_gb")
    if raw_total is None:
        raw_total = os.getenv("QUOTA_TOTAL_GB", "0")
    try:
        total_gb = float(raw_total)
    except (TypeError, ValueError):
        total_gb = 0.0

    raw_day = kv.get("quota_reset_day")
    if raw_day is None:
        raw_day = os.getenv("QUOTA_RESET_DAY", "15")
    try:
        reset_day = int(float(raw_day))
    except (TypeError, ValueError):
        reset_day = 15

    reset_time = kv.get("quota_reset_time") or os.getenv("QUOTA_RESET_TIME", "10:31")

    return {"total_gb": total_gb, "reset_day": reset_day, "reset_time": reset_time}


def total_bytes(cfg: dict) -> int:
    """套餐总量（字节）；0 表示不限，订阅里就不带 total"""
    try:
        return int(float(cfg.get("total_gb") or 0) * 1024 ** 3)
    except (TypeError, ValueError):
        return 0


def primary_iface() -> str:
    """默认路由所在网卡"""
    try:
        with open("/proc/net/route", "r") as f:
            for line in f.readlines()[1:]:
                parts = line.split()
                if len(parts) > 2 and parts[1] == "00000000":
                    return parts[0]
    except OSError:
        pass
    return os.getenv("TRAFFIC_IFACE", "eth0")


def _read_counters():
    """返回 (rx, tx) 累计字节数，读不到返回 None"""
    iface = primary_iface()
    try:
        with open("/proc/net/dev", "r") as f:
            for line in f.readlines()[2:]:
                if ":" not in line:
                    continue
                name, data = line.split(":", 1)
                if name.strip() != iface:
                    continue
                parts = data.split()
                return int(parts[0]), int(parts[8])
    except (OSError, ValueError, IndexError):
        return None
    return None


def _period_start(now: datetime, cfg: dict) -> datetime:
    """本计费周期的起点"""
    day = max(1, min(28, int(cfg.get("reset_day") or 15)))
    hh, mm = _parse_reset_time(cfg.get("reset_time"))

    def build(base: datetime) -> datetime:
        try:
            return base.replace(day=day, hour=hh, minute=mm, second=0, microsecond=0)
        except ValueError:
            return base.replace(day=1, hour=hh, minute=mm, second=0, microsecond=0)

    candidate = build(now)
    if now < candidate:
        first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        candidate = build(first_of_month - timedelta(seconds=1))
    return candidate


def _next_period_start(start: datetime) -> datetime:
    month = start.month + 1
    year = start.year
    if month > 12:
        month = 1
        year += 1
    try:
        return start.replace(year=year, month=month)
    except ValueError:
        return start.replace(year=year, month=month, day=28)


async def snapshot() -> dict:
    """本周期用量快照：upload/download/total/expire 可直接喂给 subscription-userinfo"""
    now = datetime.now(TZ)
    counters = _read_counters()

    async with get_db() as db:
        cfg = await load_config(db)
        cur_start = _period_start(now, cfg)

        cursor = await db.execute("SELECT * FROM traffic WHERE id = 1")
        row = await cursor.fetchone()

        need_reset = row is None
        if row is not None:
            try:
                saved = datetime.fromisoformat(row["period_start"])
            except (TypeError, ValueError):
                need_reset = True
            else:
                need_reset = saved < cur_start

        if need_reset:
            rx, tx = counters if counters else (0, 0)
            await db.execute("DELETE FROM traffic")
            await db.execute(
                "INSERT INTO traffic (id, period_start, rx_base, tx_base, rx_used, tx_used) "
                "VALUES (1, ?, ?, ?, 0, 0)",
                (cur_start.isoformat(), rx, tx),
            )
            await db.commit()
            rx_used = tx_used = 0
        else:
            rx_used, tx_used = row["rx_used"] or 0, row["tx_used"] or 0
            if counters:
                rx, tx = counters
                # 计数变小说明网卡（或整机）重启过：当前值当新基线，不累加负数
                d_rx = rx - (row["rx_base"] or 0)
                d_tx = tx - (row["tx_base"] or 0)
                if d_rx > 0:
                    rx_used += d_rx
                if d_tx > 0:
                    tx_used += d_tx
                await db.execute(
                    "UPDATE traffic SET rx_base = ?, tx_base = ?, rx_used = ?, tx_used = ? WHERE id = 1",
                    (rx, tx, rx_used, tx_used),
                )
                await db.commit()

    nxt = _next_period_start(cur_start)
    # 客户端（v2rayN 等）把 upload/download 分两栏显示，而中间那个 "/" 只跟在
    # download 后面，用户看到的"已用"永远是 download 那一栏。所以这里把上行
    # 并进 download 一起给，客户端显示的已用量才和面板、服务商控制台一致。
    # 内部仍分开记账（rx_used / tx_used），需要看单向明细时取原始字段即可。
    return {
        "upload": 0,
        "download": rx_used + tx_used,
        "total": total_bytes(cfg),
        "expire": int(nxt.timestamp()),
        "period_start": cur_start.isoformat(),
        "period_end": nxt.isoformat(),
        "iface": primary_iface(),
        "total_gb": cfg["total_gb"],
        "reset_day": cfg["reset_day"],
        "reset_time": cfg["reset_time"],
    }


async def save_config(values: dict) -> dict:
    """保存套餐参数（只认 SETTING_KEYS 里的字段）"""
    async with get_db() as db:
        for field, col in SETTING_KEYS.items():
            value = values.get(field)
            if value is None:
                continue
            await db.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (col, str(value)),
            )
        await db.commit()
    return await snapshot()


async def align_used(used_gb: float) -> dict:
    """把本周期已用量对齐到服务商控制台显示的值（差额记到下行）"""
    target = int(round(float(used_gb) * 1024 ** 3))
    await snapshot()  # 确保 traffic 行存在

    async with get_db() as db:
        cursor = await db.execute("SELECT rx_used, tx_used FROM traffic WHERE id = 1")
        row = await cursor.fetchone()
        rx_used = (row["rx_used"] or 0) if row else 0
        tx_used = (row["tx_used"] or 0) if row else 0
        delta = target - (rx_used + tx_used)
        # 代理流量以下载为主，差额记到 tx_used（= 客户端下载）
        new_tx = max(0, tx_used + delta)
        await db.execute("UPDATE traffic SET tx_used = ? WHERE id = 1", (new_tx,))
        await db.commit()

    return await snapshot()
