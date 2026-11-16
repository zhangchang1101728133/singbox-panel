"""流量统计：按计费周期累计网卡收发字节

数据源是 /proc/net/dev —— 面板容器用 host 网络，读到的就是宿主机网卡。
网卡累计值会随重启归零，所以这里把每次读到的增量累加进数据库，
并用 period_start 区分计费周期，避免重启和跨周期算错。
"""

import os
from datetime import datetime, timedelta, timezone

from ..models.database import get_db

# 计费周期按服务商所在时区算（服务商给的重置时间是 UTC+8）
TZ = timezone(timedelta(hours=8))


def _reset_day() -> int:
    try:
        return int(os.getenv("QUOTA_RESET_DAY", "15"))
    except ValueError:
        return 15


def _reset_time() -> tuple:
    raw = os.getenv("QUOTA_RESET_TIME", "10:31")
    try:
        hh, mm = raw.split(":")
        return int(hh), int(mm)
    except (ValueError, AttributeError):
        return 10, 31


def total_bytes() -> int:
    """套餐总量（字节）；QUOTA_TOTAL_GB=0 表示不限，订阅里就不带 total"""
    try:
        gb = float(os.getenv("QUOTA_TOTAL_GB", "0") or 0)
    except ValueError:
        return 0
    return int(gb * 1024 ** 3)


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


def _period_start(now: datetime) -> datetime:
    """本计费周期的起点"""
    day = _reset_day()
    hh, mm = _reset_time()

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
    cur_start = _period_start(now)
    counters = _read_counters()

    async with get_db() as db:
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
    return {
        "upload": tx_used,
        "download": rx_used,
        "total": total_bytes(),
        "expire": int(nxt.timestamp()),
        "period_start": cur_start.isoformat(),
        "period_end": nxt.isoformat(),
        "iface": primary_iface(),
    }
