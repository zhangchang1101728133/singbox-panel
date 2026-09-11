"""节点管理路由（纯 JSON API）"""
import json
import logging
from typing import List, Optional
from pydantic import BaseModel, field_validator

from fastapi import APIRouter, Depends, HTTPException

from .auth import get_current_user
from ..models.database import get_db
from ..services.singbox import SingboxService
from ..services import protocols

router = APIRouter()
logger = logging.getLogger(__name__)

SUPPORTED_TYPES = protocols.supported_ids()


class NodeCreate(BaseModel):
    name: str
    type: str
    server: str
    server_port: int
    config: dict
    enabled: bool = True

    @field_validator('type')
    @classmethod
    def validate_type(cls, v):
        if v not in SUPPORTED_TYPES:
            raise ValueError(f'不支持的协议: {v}')
        return v

    @field_validator('server_port')
    @classmethod
    def validate_port(cls, v):
        if not (1 <= v <= 65535):
            raise ValueError('端口必须在 1-65535 之间')
        return v

    @field_validator('name', 'server')
    @classmethod
    def validate_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('不能为空')
        return v.strip()


class NodeUpdate(BaseModel):
    name: Optional[str] = None
    server: Optional[str] = None
    server_port: Optional[int] = None
    config: Optional[dict] = None
    enabled: Optional[bool] = None

    @field_validator('server_port')
    @classmethod
    def validate_port(cls, v):
        if v is not None and not (1 <= v <= 65535):
            raise ValueError('端口必须在 1-65535 之间')
        return v


@router.get("/api")
async def list_nodes(user: dict = Depends(get_current_user)):
    """节点列表（JSON）"""
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM nodes ORDER BY created_at DESC")
        nodes = [dict(row) for row in await cursor.fetchall()]
    for node in nodes:
        if isinstance(node.get("config"), str):
            node["config"] = json.loads(node["config"])
        node["enabled"] = bool(node["enabled"])
    return nodes


@router.post("/api/add")
async def add_node(node: NodeCreate, user: dict = Depends(get_current_user)):
    """添加节点：先把新节点并入现有配置做校验，通过后才写库"""
    async with get_db() as db:
        existing = await _load_nodes(db)
        candidate = existing + [{
            "id": 0, "name": node.name, "type": node.type,
            "server": node.server, "server_port": node.server_port,
            "enabled": node.enabled, "config": node.config,
        }]
        await _ensure_valid(candidate)

        await db.execute(
            "INSERT INTO nodes (name, type, server, server_port, config, enabled) VALUES (?, ?, ?, ?, ?, ?)",
            (node.name, node.type, node.server, node.server_port, json.dumps(node.config), node.enabled)
        )
        await db.commit()
        await regenerate_configs(db)
    return {"message": "节点添加成功"}


@router.put("/api/{node_id}")
async def update_node(node_id: int, node: NodeUpdate, user: dict = Depends(get_current_user)):
    """更新节点：同样先校验合并后的配置，再写库"""
    async with get_db() as db:
        nodes = await _load_nodes(db)
        target = next((n for n in nodes if n["id"] == node_id), None)
        if target is None:
            raise HTTPException(status_code=404, detail="节点不存在")

        # 在副本上套用本次修改，用于生成待校验的配置
        merged = dict(target)
        for key in ("name", "server", "server_port", "config", "enabled"):
            value = getattr(node, key)
            if value is not None:
                merged[key] = value
        candidate = [merged if n["id"] == node_id else n for n in nodes]
        await _ensure_valid(candidate)

        updates, params = [], []
        if node.name is not None:
            updates.append("name = ?"); params.append(node.name)
        if node.server is not None:
            updates.append("server = ?"); params.append(node.server)
        if node.server_port is not None:
            updates.append("server_port = ?"); params.append(node.server_port)
        if node.config is not None:
            updates.append("config = ?"); params.append(json.dumps(node.config))
        if node.enabled is not None:
            updates.append("enabled = ?"); params.append(node.enabled)

        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(node_id)
            await db.execute(f"UPDATE nodes SET {', '.join(updates)} WHERE id = ?", params)
            await db.commit()
            await regenerate_configs(db)
    return {"message": "节点更新成功"}


@router.delete("/api/{node_id}")
async def delete_node(node_id: int, user: dict = Depends(get_current_user)):
    """删除节点"""
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM nodes WHERE id = ?", (node_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="节点不存在")
        await db.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
        await db.commit()
        await regenerate_configs(db)
    return {"message": "节点删除成功"}


async def _load_nodes(db) -> List[dict]:
    """读取全部节点并解析 config JSON"""
    cursor = await db.execute("SELECT * FROM nodes")
    nodes = [dict(row) for row in await cursor.fetchall()]
    for node in nodes:
        if isinstance(node.get("config"), str):
            node["config"] = json.loads(node["config"])
    return nodes


async def _ensure_valid(nodes: List[dict]):
    """校验一组节点能否生成被 sing-box 接受的配置，不通过直接 400"""
    ok, msg = await SingboxService.validate_generated(
        SingboxService.generate_server_config(nodes)
    )
    if not ok:
        logger.error("配置校验失败: %s", msg)
        raise HTTPException(status_code=400, detail=f"配置校验失败，未保存：{msg}")


async def regenerate_configs(db):
    """重新生成所有配置文件，校验通过后重启 sing-box

    写入前先备份：新配置若不被当前 sing-box 接受，回滚到备份并报错，
    避免一次误操作把正在跑的代理搞挂。
    """
    nodes = await _load_nodes(db)

    backup = SingboxService.backup_config()
    server_config = SingboxService.generate_server_config(nodes)
    SingboxService.save_config(server_config)

    ok, msg = await SingboxService.validate_config()
    if not ok:
        SingboxService.restore_config(backup)
        logger.error("生成的配置未通过校验，已回滚: %s", msg)
        raise HTTPException(status_code=400, detail=f"配置校验失败，已回滚：{msg}")

    cursor = await db.execute("SELECT * FROM subscriptions WHERE enabled = TRUE")
    subs = [dict(row) for row in await cursor.fetchall()]
    for sub in subs:
        sub_node_ids = json.loads(sub["node_ids"]) if isinstance(sub["node_ids"], str) else sub["node_ids"]
        sub_nodes = [n for n in nodes if n["id"] in sub_node_ids] if sub_node_ids else nodes
        client_config = SingboxService.generate_client_config(sub_nodes)
        SingboxService.save_subscription(client_config, sub["id"])

    await SingboxService.restart()



