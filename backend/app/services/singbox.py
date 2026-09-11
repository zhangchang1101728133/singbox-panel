"""sing-box 配置生成和管理服务"""
import asyncio
import json
import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from . import protocols

logger = logging.getLogger(__name__)

# 运行 sing-box 的容器名 / 镜像，均可通过环境变量覆盖
CONTAINER_NAME = os.getenv("SINGBOX_CONTAINER", "sing-box")
SINGBOX_IMAGE = os.getenv("SINGBOX_IMAGE", "ghcr.io/sagernet/sing-box")
# 面板在 sing-box 容器内看到的挂载路径
CONTAINER_CONFIG_DIR = os.getenv("SINGBOX_CONFIG_DIR", "/etc/sing-box")
SUBPROCESS_TIMEOUT = 120


class SingboxService:
    """sing-box 配置服务"""

    CONFIG_DIR = Path(os.getenv("DATA_DIR", "/data")) / "config"
    SUB_DIR = Path(os.getenv("DATA_DIR", "/data")) / "sub"

    # ── 配置生成 ────────────────────────────────────────────

    @classmethod
    def generate_client_config(cls, nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """生成客户端订阅配置"""
        outbounds = []

        for node in nodes:
            if not node.get("enabled", True):
                continue
            if not protocols.get_protocol(node["type"]):
                logger.warning("跳过未知协议节点: %s (%s)", node.get("name"), node.get("type"))
                continue

            outbound = protocols.build_outbound(node)
            outbound["tag"] = node["name"]
            outbounds.append(outbound)

        node_tags = [o["tag"] for o in outbounds]

        all_outbounds = [
            {
                "type": "selector",
                "tag": "proxy",
                "outbounds": ["auto"] + node_tags,
                "default": "auto"
            },
            {
                "type": "urltest",
                "tag": "auto",
                "outbounds": node_tags,
                "url": "http://www.gstatic.com/generate_204",
                "interval": "3m",
                "tolerance": 50
            },
        ] + outbounds + [
            {"type": "direct", "tag": "direct"}
        ]

        return {
            "dns": {
                "servers": [
                    # 走代理解析：查国外域名不会被污染
                    {"tag": "proxy-dns", "type": "tls", "server": "8.8.8.8", "detour": "proxy"},
                    # 直连解析：用于解析「代理服务器自己的域名」和国内域名。
                    # 用阿里 DNS 而不是 114：114 会对不存在的域名做劫持，用它解析代理域名有风险。
                    {"tag": "local", "type": "udp", "server": "223.5.5.5"}
                ],
                "rules": [
                    {"domain_suffix": [".cn"], "server": "local"}
                ],
                "strategy": "prefer_ipv4"
            },
            "inbounds": [
                {
                    "type": "tun",
                    "tag": "tun-in",
                    "address": ["172.19.0.1/30", "fdfe:dcba:9876::1/126"],
                    "auto_route": True,
                    "strict_route": True,
                    "stack": "mixed"
                },
                {
                    "type": "mixed",
                    "tag": "mixed-in",
                    "listen": "127.0.0.1",
                    "listen_port": 2080
                }
            ],
            "outbounds": all_outbounds,
            "route": {
                # 必须是「直连」解析器！
                # 这个字段用来解析 outbound 的服务器域名。如果指向 proxy-dns（detour=proxy），
                # 就会形成循环依赖：连代理前要先解析代理的域名，而解析又要先连上代理。
                # 症状很隐蔽 —— urltest 全部解析超时（auto 失效）、新建连接超时，
                # 表现为「浏览勉强能用、下载这种多连接场景直接卡死」。
                "default_domain_resolver": {"server": "local"},
                "rules": [
                    {"inbound": "tun-in", "action": "sniff", "timeout": "1s"},
                    {"inbound": "mixed-in", "action": "sniff", "timeout": "1s"},
                    {"action": "hijack-dns", "protocol": "dns"},
                    {"domain_suffix": ["cn"], "outbound": "direct"},
                    {"domain_suffix": [
                        "bilibili.com", "biliapi.net", "jd.com", "taobao.com",
                        "tmall.com", "alipay.com", "alicdn.com", "163.com",
                        "126.net", "qq.com", "weixin.qq.com", "tencent.com",
                        "baidu.com", "bdstatic.com"
                    ], "outbound": "direct"},
                    {"ip_cidr": [
                        "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10",
                        "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12",
                        "192.168.0.0/16", "::1/128", "fc00::/7", "fe80::/10"
                    ], "outbound": "direct"}
                ],
                "final": "proxy",
                "auto_detect_interface": True
            }
        }

    @classmethod
    def generate_server_config(cls, nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """生成服务端配置"""
        inbounds = []

        for node in nodes:
            if not node.get("enabled", True):
                continue
            if not protocols.get_protocol(node["type"]):
                logger.warning("跳过未知协议节点: %s (%s)", node.get("name"), node.get("type"))
                continue

            inbound = protocols.build_inbound(node)
            inbound["tag"] = node["name"]
            inbound["listen"] = "::"
            inbound["listen_port"] = node["server_port"]
            inbounds.append(inbound)

        return {
            "log": {"level": "info", "timestamp": True},
            "inbounds": inbounds,
            "outbounds": [
                {"type": "direct", "tag": "direct"}
            ],
            "route": {
                "rules": [
                    {"action": "hijack-dns", "protocol": "dns"},
                    {"ip_cidr": [
                        "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10",
                        "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12",
                        "192.168.0.0/16", "::1/128", "fc00::/7", "fe80::/10"
                    ], "outbound": "direct"}
                ],
                "final": "direct",
                "auto_detect_interface": True
            }
        }

    # ── 文件读写 ────────────────────────────────────────────

    @classmethod
    def save_config(cls, config: Dict[str, Any], filename: str = "config.json"):
        """保存配置到文件"""
        cls.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        config_path = cls.CONFIG_DIR / filename
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return config_path

    @classmethod
    def subscription_path(cls, sub_id: int) -> Path:
        """订阅文件路径

        文件名用自增 id，**不要**用 token：token 是访问凭据、可以轮换，
        文件名跟着 token 走的话改 token 就得迁移文件；更要紧的是，
        写文件和读文件的两处若各自拼名字，很容易分叉成两个文件
        —— 曾经就因此让下载接口一直返回旧配置。
        """
        return cls.SUB_DIR / f"sub_{sub_id}.json"

    @classmethod
    def save_subscription(cls, config: Dict[str, Any], sub_id: int):
        """保存订阅文件（按订阅 id 命名，见 subscription_path）"""
        cls.SUB_DIR.mkdir(parents=True, exist_ok=True)
        sub_path = cls.subscription_path(sub_id)
        with open(sub_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return sub_path

    @classmethod
    def backup_config(cls) -> Optional[Path]:
        """备份当前 config.json，返回备份路径"""
        config_path = cls.CONFIG_DIR / "config.json"
        if not config_path.exists():
            return None
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = cls.CONFIG_DIR / f"config.json.bak-{stamp}"
        shutil.copy2(config_path, backup_path)
        cls._prune_backups()
        return backup_path

    @classmethod
    def restore_config(cls, backup_path: Optional[Path]):
        """从备份恢复 config.json"""
        if backup_path and Path(backup_path).exists():
            shutil.copy2(backup_path, cls.CONFIG_DIR / "config.json")

    @classmethod
    def _prune_backups(cls, keep: int = 5):
        backups = sorted(cls.CONFIG_DIR.glob("config.json.bak-*"))
        for old in backups[:-keep]:
            old.unlink(missing_ok=True)

    # ── 容器控制 ────────────────────────────────────────────

    @staticmethod
    async def _run(*args, timeout: int = SUBPROCESS_TIMEOUT):
        """执行本地命令，返回 (returncode, stdout, stderr)"""
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return proc.returncode, out.decode(errors="replace"), err.decode(errors="replace")
        except asyncio.TimeoutError:
            return 124, "", f"命令超时（{timeout}s）: {' '.join(args)}"
        except FileNotFoundError:
            return 127, "", f"命令不存在: {args[0]}"
        except Exception as e:  # noqa: BLE001
            return 1, "", str(e)

    @classmethod
    async def container_running(cls) -> bool:
        code, _, _ = await cls._run("docker", "inspect", CONTAINER_NAME, timeout=15)
        return code == 0

    @classmethod
    async def validate_config(cls, filename: str = "config.json") -> tuple:
        """用 sing-box check 校验配置，返回 (ok, message)

        sing-box 二进制只存在于 sing-box 镜像内，因此校验在容器里执行。
        容器未运行时跳过校验，避免阻塞配置写入。
        """
        if not await cls.container_running():
            return True, "容器未运行，跳过校验"

        container_path = f"{CONTAINER_CONFIG_DIR}/{filename}"
        code, out, err = await cls._run(
            "docker", "exec", CONTAINER_NAME, "sing-box", "check", "-c", container_path,
            timeout=30
        )
        if code == 0:
            return True, "配置校验通过"
        return False, (err or out or "配置校验失败").strip()

    @classmethod
    async def validate_generated(cls, config: Dict[str, Any]) -> tuple:
        """校验尚未落盘的配置：写临时文件 → check → 删除临时文件

        用于在写库之前判断这份配置能不能被当前 sing-box 接受。
        """
        if not await cls.container_running():
            return True, "容器未运行，跳过校验"

        tmp_name = "config.check.json"
        cls.save_config(config, tmp_name)
        try:
            return await cls.validate_config(tmp_name)
        finally:
            (cls.CONFIG_DIR / tmp_name).unlink(missing_ok=True)

    @classmethod
    async def restart(cls):
        """重启 sing-box 容器，使其加载新写入的 config.json"""
        code, _, err = await cls._run("docker", "restart", CONTAINER_NAME, timeout=60)
        if code != 0:
            logger.error("重启 sing-box 失败: %s", err)
            raise RuntimeError(err.strip() or "重启 sing-box 失败")
        return True

    # ── 版本信息 ────────────────────────────────────────────

    @classmethod
    async def get_running_version(cls) -> Optional[str]:
        """读取运行中 sing-box 的版本号，读不到返回 None"""
        code, out, _ = await cls._run(
            "docker", "exec", CONTAINER_NAME, "sing-box", "version", timeout=20
        )
        if code != 0:
            return None
        m = re.search(r"(\d+\.\d+\.\d+)", out)
        return m.group(1) if m else None

    @staticmethod
    def get_server_ip() -> str:
        """获取服务器公网 IP：优先用环境变量，避免每次都走外网探测"""
        configured = os.getenv("SERVER_IP", "")
        if configured and configured != "auto":
            return configured
        try:
            import httpx
            resp = httpx.get("https://api.ipify.org", timeout=5)
            return resp.text.strip()
        except Exception:
            return configured or "127.0.0.1"
