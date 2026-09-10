"""API 路由"""
import asyncio
import json
import secrets
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .auth import get_current_user
from ..models.database import get_db
from ..services.singbox import SingboxService, CONTAINER_NAME
from ..services import protocols
from ..services.updater import SingboxUpdater

router = APIRouter()


class QuickSetupRequest(BaseModel):
    server: str
    sni: str = protocols.DEFAULT_REALITY_SNI
    protocols: List[str] = []


@router.get("/protocols")
async def list_protocols(user: dict = Depends(get_current_user)):
    """协议清单：按当前 sing-box 版本标记 available，前端据此隐藏不支持的协议"""
    running = await SingboxService.get_running_version()
    return {
        "core_version": running,
        "protocols": protocols.protocol_list(running),
    }


class RandomRequest(BaseModel):
    field: str
    config: dict = {}


@router.post("/protocols/{protocol_id}/random")
async def random_field_value(protocol_id: str, req: RandomRequest, user: dict = Depends(get_current_user)):
    """为表单字段生成随机值（Shadowsocks 2022 的密钥格式依赖加密方式，故由后端生成）"""
    if protocol_id not in protocols.supported_ids():
        raise HTTPException(status_code=404, detail="未知协议")
    return {"value": protocols.random_value(protocol_id, req.field, req.config)}


@router.get("/server-info")
async def server_info(user: dict = Depends(get_current_user)):
    """服务器信息：公网 IP（前端拼订阅链接用）"""
    return {"server_ip": SingboxService.get_server_ip()}


@router.get("/stats")
async def get_stats(user: dict = Depends(get_current_user)):
    """获取系统统计"""
    async with get_db() as db:
        cursor = await db.execute("""
            SELECT
                (SELECT COUNT(*) FROM nodes) as total_nodes,
                (SELECT COUNT(*) FROM nodes WHERE enabled = TRUE) as active_nodes,
                (SELECT COUNT(*) FROM subscriptions) as total_subs,
                (SELECT COUNT(*) FROM subscriptions WHERE enabled = TRUE) as active_subs
        """)
        row = await cursor.fetchone()
        return dict(row)


@router.get("/export")
async def export_config(user: dict = Depends(get_current_user)):
    """导出所有配置"""
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM nodes")
        nodes = [dict(row) for row in await cursor.fetchall()]
        for node in nodes:
            if isinstance(node.get("config"), str):
                node["config"] = json.loads(node["config"])

        cursor = await db.execute("SELECT * FROM subscriptions")
        subs = [dict(row) for row in await cursor.fetchall()]

    return {"nodes": nodes, "subscriptions": subs}


@router.post("/clear-all")
async def clear_all(user: dict = Depends(get_current_user)):
    """清空所有节点和订阅"""
    sub_dir = SingboxService.SUB_DIR
    if sub_dir.exists():
        for f in sub_dir.glob("*.json"):
            f.unlink()

    async with get_db() as db:
        await db.execute("DELETE FROM nodes")
        await db.execute("DELETE FROM subscriptions")
        await db.commit()

    config = {
        "log": {"level": "info", "timestamp": True},
        "inbounds": [],
        "outbounds": [
            {"type": "direct", "tag": "direct"}
        ],
        "route": {
            "rules": [{"action": "hijack-dns", "protocol": "dns"}],
            "final": "direct",
            "auto_detect_interface": True
        }
    }
    SingboxService.save_config(config)
    await SingboxService.restart()

    return {"message": "已清空所有配置"}


@router.get("/singbox/version")
async def get_singbox_version(user: dict = Depends(get_current_user)):
    """sing-box 版本信息：本地版本 + GitHub 最新 release，不做 docker pull"""
    return await SingboxUpdater.status()


@router.post("/singbox/update")
async def update_singbox(user: dict = Depends(get_current_user)):
    """升级 sing-box：备份 → 拉镜像 → compose 重建 → 校验 → 失败自动回滚"""
    try:
        return await SingboxUpdater.update()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"更新失败: {e}")


@router.post("/quick-setup")
async def quick_setup(req: QuickSetupRequest, user: dict = Depends(get_current_user)):
    """一键配置：按选中的协议生成节点 + 默认订阅"""
    async with get_db() as db:
        cursor = await db.execute("SELECT COUNT(*) FROM nodes")
        count = (await cursor.fetchone())[0]
        if count > 0:
            raise HTTPException(status_code=400, detail="已有节点配置，请先清空或手动添加")

        core_version = await SingboxService.get_running_version()

        # 未显式选择时，使用当前核心支持的全部协议
        wanted = req.protocols or list(protocols.supported_ids())
        selected = [p for p in wanted if protocols.is_supported(p, core_version)]
        unsupported = [p for p in wanted if p not in selected]
        if not selected:
            raise HTTPException(status_code=400, detail="没有当前 sing-box 版本支持的协议")

        # VLESS 需要 Reality 密钥对
        reality = await _generate_reality_keypair() if "vless" in selected else {}

        candidate = []
        for proto_id in selected:
            proto = protocols.get_protocol(proto_id)
            candidate.append({
                "id": 0,
                "name": proto["label"],
                "type": proto_id,
                "server": req.server,
                "server_port": proto["default_port"],
                "enabled": True,
                "config": proto["defaults"](sni=req.sni, reality=reality),
            })

        # 写库前先校验，避免生成 sing-box 起不来的配置
        ok, msg = await SingboxService.validate_generated(
            SingboxService.generate_server_config(candidate)
        )
        if not ok:
            raise HTTPException(status_code=400, detail=f"配置校验失败，未保存：{msg}")

        created = []
        for node in candidate:
            await db.execute(
                "INSERT INTO nodes (name, type, server, server_port, config, enabled) VALUES (?, ?, ?, ?, ?, TRUE)",
                (node["name"], node["type"], node["server"], node["server_port"], json.dumps(node["config"]))
            )
            created.append(node["type"])
        await db.commit()

        # 创建默认订阅（用 ID 作为文件名）
        cursor = await db.execute(
            "INSERT INTO subscriptions (user_id, name, token, slug, node_ids, enabled) VALUES (?, ?, '', '', '[]', TRUE)",
            (user["id"], "默认订阅")
        )
        sub_id = cursor.lastrowid
        sub_token = f"sub_{sub_id}"
        await db.execute("UPDATE subscriptions SET token = ? WHERE id = ?", (sub_token, sub_id))
        await db.commit()

        # 生成订阅文件
        cursor = await db.execute("SELECT * FROM nodes")
        nodes = [dict(row) for row in await cursor.fetchall()]
        for node in nodes:
            if isinstance(node.get("config"), str):
                node["config"] = json.loads(node["config"])

        client_config = SingboxService.generate_client_config(nodes)
        SingboxService.save_subscription(client_config, sub_token)

        # 生成服务端配置并重启
        server_config = SingboxService.generate_server_config(nodes)
        SingboxService.save_config(server_config)
        await SingboxService.restart()

    message = f"已成功配置 {len(created)} 个协议节点"
    if unsupported:
        message += f"（{', '.join(unsupported)} 需要更高版本 sing-box，已跳过）"

    return {"message": message, "sub_token": sub_token, "created": created, "skipped": unsupported}


async def _generate_reality_keypair() -> dict:
    """调用 sing-box 生成 Reality 密钥对"""
    proc = await asyncio.create_subprocess_exec(
        "docker", "exec", CONTAINER_NAME, "sing-box", "generate", "reality-keypair",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail="生成 Reality 密钥失败，请确认 sing-box 容器正在运行")

    lines = stdout.decode().strip().split("\n")
    private_key = lines[0].split(":")[-1].strip() if len(lines) > 0 else ""
    public_key = lines[1].split(":")[-1].strip() if len(lines) > 1 else ""
    return {
        "enabled": True,
        "public_key": public_key,
        "private_key": private_key,
        "short_id": secrets.token_hex(8),
    }
