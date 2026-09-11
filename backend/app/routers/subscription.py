"""订阅管理路由（纯 JSON API）"""
import json
import secrets
from typing import List
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from .auth import get_current_user
from ..models.database import get_db
from ..services.singbox import SingboxService

router = APIRouter()


class SubscriptionCreate(BaseModel):
    name: str
    node_ids: List[int] = []
    slug: str = ""


def _new_token() -> str:
    """订阅 token

    下载接口 /sub/download/{token} 是**未认证**的，token 就是唯一的访问凭据，
    所以必须不可枚举（早期版本用 f"sub_{id}"，等于把全部节点凭据公开）。
    """
    return secrets.token_urlsafe(24)


def _sub_file(sub_id: int):
    """订阅文件路径

    文件名用自增 id 而不是 token：id 不进 URL、不承担鉴权，token 可以随时轮换
    而不必迁移文件。鉴权只发生在下载接口的 token → id 查表这一步。
    """
    return SingboxService.SUB_DIR / f"sub_{sub_id}.json"


@router.get("/api")
async def list_subscriptions(user: dict = Depends(get_current_user)):
    """订阅列表（JSON）"""
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM subscriptions ORDER BY created_at DESC")
        subs = [dict(row) for row in await cursor.fetchall()]
    for sub in subs:
        if isinstance(sub.get("node_ids"), str):
            sub["node_ids"] = json.loads(sub["node_ids"]) if sub["node_ids"] else []
        sub["enabled"] = bool(sub["enabled"])
    return subs


@router.post("/api/add")
async def add_subscription(sub: SubscriptionCreate, user: dict = Depends(get_current_user)):
    """添加订阅"""
    async with get_db() as db:
        if sub.slug:
            cursor = await db.execute("SELECT id FROM subscriptions WHERE slug = ?", (sub.slug,))
            if await cursor.fetchone():
                raise HTTPException(status_code=400, detail="该链接别名已存在")

        token = _new_token()
        cursor = await db.execute(
            "INSERT INTO subscriptions (user_id, name, token, slug, node_ids) VALUES (?, ?, ?, ?, ?)",
            (user["id"], sub.name, token, sub.slug, json.dumps(sub.node_ids))
        )
        sub_id = cursor.lastrowid
        await db.commit()
        await _generate_sub_file(db, sub_id, sub.node_ids)

    return {"message": "订阅创建成功", "id": sub_id, "token": token}


@router.put("/api/{sub_id}")
async def update_subscription(sub_id: int, sub: SubscriptionCreate, user: dict = Depends(get_current_user)):
    """更新订阅"""
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM subscriptions WHERE id = ?", (sub_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="订阅不存在")

        if sub.slug:
            cursor = await db.execute("SELECT id FROM subscriptions WHERE slug = ? AND id != ?", (sub.slug, sub_id))
            if await cursor.fetchone():
                raise HTTPException(status_code=400, detail="该链接别名已存在")

        await db.execute(
            "UPDATE subscriptions SET name = ?, slug = ?, node_ids = ? WHERE id = ?",
            (sub.name, sub.slug, json.dumps(sub.node_ids), sub_id)
        )
        await db.commit()
        await _generate_sub_file(db, sub_id, sub.node_ids)

    return {"message": "订阅更新成功"}


@router.delete("/api/{sub_id}")
async def delete_subscription(sub_id: int, user: dict = Depends(get_current_user)):
    """删除订阅"""
    async with get_db() as db:
        cursor = await db.execute("SELECT id FROM subscriptions WHERE id = ?", (sub_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="订阅不存在")
        _sub_file(sub_id).unlink(missing_ok=True)
        await db.execute("DELETE FROM subscriptions WHERE id = ?", (sub_id,))
        await db.commit()
    return {"message": "订阅删除成功"}


@router.get("/download/{name}")
async def download_subscription(name: str):
    """下载订阅配置 - 支持 token 或 slug 访问（未认证，靠不可枚举的 token 鉴权）"""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, enabled FROM subscriptions WHERE slug = ? OR token = ?", (name, name)
        )
        sub = await cursor.fetchone()
        if not sub or not sub["enabled"]:
            raise HTTPException(status_code=404, detail="订阅不存在")

    sub_path = _sub_file(sub["id"])
    if not sub_path.exists():
        raise HTTPException(status_code=404, detail="订阅文件不存在")
    with open(sub_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    return JSONResponse(content=config)


async def _generate_sub_file(db, sub_id: int, node_ids: List[int]):
    """生成订阅文件"""
    cursor = await db.execute("SELECT * FROM nodes")
    nodes = [dict(row) for row in await cursor.fetchall()]
    for node in nodes:
        if isinstance(node.get("config"), str):
            node["config"] = json.loads(node["config"])
    sub_nodes = [n for n in nodes if n["id"] in node_ids] if node_ids else nodes
    client_config = SingboxService.generate_client_config(sub_nodes)
    SingboxService.save_subscription(client_config, f"sub_{sub_id}")  # 与 _sub_file 保持一致


