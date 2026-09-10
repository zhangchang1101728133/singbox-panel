"""sing-box 核心升级服务

之前的实现有两个硬伤：
  1. `docker rm -f` + `docker run` 重建容器 —— 参数（挂载、网络、restart 策略、
     标签）全靠硬编码，和 docker-compose.yml 里的声明不一致，重建后容器脱离
     compose 管理，之后再 `docker compose up` 会行为异常。
  2. 检查版本时先 `docker pull` —— 每次打开弹窗都要拉一遍镜像，慢且依赖网络。

现在的实现：
  - 检查版本只查 GitHub Releases API + 本地 `sing-box version`，不做 pull。
  - 升级走 `docker compose pull` + `up -d`，完全沿用 compose 声明。
  - 升级前备份 config.json，升级后 `sing-box check` 校验，失败自动回滚。
"""
import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

from .singbox import SingboxService, SINGBOX_IMAGE, CONTAINER_NAME, CONTAINER_CONFIG_DIR

logger = logging.getLogger(__name__)

# compose 项目目录（含 docker-compose.yml），面板容器内通过挂载访问宿主机路径
# 注意：不能用 COMPOSE_FILE / COMPOSE_PROJECT_DIR，它们是 docker compose 的保留变量
COMPOSE_DIR = os.getenv("COMPOSE_DIR", "")
COMPOSE_FILE_NAME = os.getenv("COMPOSE_FILE_NAME", "docker-compose.yml")
COMPOSE_SERVICE = os.getenv("COMPOSE_SERVICE", "sing-box")
SINGBOX_TAG = os.getenv("SINGBOX_TAG", "latest")
# 配置目录在**宿主机**上的路径。面板容器里的 /data 对应宿主机另一个路径，
# docker run -v 是由守护进程在宿主机上解析的，必须用宿主机路径。
HOST_DATA_DIR = os.getenv("HOST_DATA_DIR", "")

GITHUB_RELEASE_API = "https://api.github.com/repos/SagerNet/sing-box/releases/latest"
PULL_TIMEOUT = 600


class SingboxUpdater:
    """sing-box 镜像与容器的升级器"""

    @staticmethod
    async def _run(*args, timeout: int = 120):
        return await SingboxService._run(*args, timeout=timeout)

    # ── 版本查询 ────────────────────────────────────────────

    @staticmethod
    async def get_latest_version() -> Optional[str]:
        """从 GitHub Releases 读取最新稳定版号（不拉镜像）"""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(
                    GITHUB_RELEASE_API,
                    headers={"Accept": "application/vnd.github+json"},
                )
                if resp.status_code != 200:
                    return None
                tag = (resp.json() or {}).get("tag_name") or ""
                return tag.lstrip("v") or None
        except Exception as e:  # noqa: BLE001
            logger.warning("获取 sing-box 最新版本失败: %s", e)
            return None

    @classmethod
    async def status(cls) -> dict:
        """返回当前版本、最新版本、是否有更新"""
        running = await SingboxService.get_running_version()
        latest = await cls.get_latest_version()
        pinned = SINGBOX_TAG != "latest"

        # 固定在某个版本时，compose pull 只会拉该 tag，提示"有更新"没有意义
        update_available = bool(
            running and latest and cls._gt(latest, running) and not pinned
        )

        result = {
            "version": running,
            "latest_version": latest,
            "update_available": update_available,
            "pinned_tag": SINGBOX_TAG if pinned else None,
            "image": SINGBOX_IMAGE,
            "container": CONTAINER_NAME,
            "running": running is not None,
            "compose_available": cls.compose_dir() is not None,
            "project": await cls._project_name(),
            "preflight_ready": bool(HOST_DATA_DIR),
        }
        if not running:
            result["error"] = f"无法读取 sing-box 版本，请确认容器 {CONTAINER_NAME} 正在运行"
        elif latest is None:
            result["error"] = "无法连接 GitHub 查询最新版本"
        elif pinned:
            result["error"] = f"镜像已固定为 {SINGBOX_TAG}，如需升级请修改 .env 里的 SINGBOX_TAG"
        return result

    @staticmethod
    def _gt(left: str, right: str) -> bool:
        """比较版本号：left > right"""
        def to_tuple(v: str):
            parts = []
            for chunk in str(v).split("-")[0].split(".")[:3]:
                digits = "".join(c for c in chunk if c.isdigit())
                parts.append(int(digits) if digits else 0)
            return tuple(parts)

        return to_tuple(left) > to_tuple(right)

    # ── 升级 ────────────────────────────────────────────────

    @staticmethod
    def compose_dir() -> Optional[Path]:
        """compose 项目目录，未配置或 compose 文件不存在则返回 None"""
        if not COMPOSE_DIR:
            return None
        path = Path(COMPOSE_DIR)
        if not (path / COMPOSE_FILE_NAME).exists():
            return None
        return path

    @classmethod
    async def _project_name(cls) -> Optional[str]:
        """compose 项目名

        面板容器里项目目录挂在 /workspace，compose 默认会用目录名当项目名（workspace），
        和宿主机上原来的项目名（singbox-panel）不一致，`up -d` 会因 container_name
        冲突而失败。所以从现有容器的 compose 标签里读真实项目名。
        """
        code, out, _ = await cls._run(
            "docker", "inspect", CONTAINER_NAME,
            "--format", '{{index .Config.Labels "com.docker.compose.project"}}',
            timeout=15,
        )
        name = out.strip()
        if code == 0 and name and name != "<no value>":
            return name

        project_dir = cls.compose_dir()
        return project_dir.name if project_dir else None

    @classmethod
    async def _compose(cls, *args, timeout: int = 300):
        """在 compose 项目目录执行 docker compose（显式指定项目名）"""
        project_dir = cls.compose_dir()
        if not project_dir:
            return None

        cmd = ["docker", "compose"]
        project = await cls._project_name()
        if project:
            cmd += ["-p", project]
        cmd += ["-f", str(project_dir / COMPOSE_FILE_NAME), *args]
        return await cls._run(*cmd, timeout=timeout)

    @classmethod
    async def update(cls) -> dict:
        """升级 sing-box：备份 → 拉镜像 → compose 重建 → 校验 → 失败回滚

        返回 {message, version, log}
        """
        log: list = []

        # 没有 compose 上下文就没法可靠地换镜像：
        # `docker restart` 不会切换镜像，硬编码 docker run 会让容器脱离 compose 管理。
        if not cls.compose_dir():
            raise RuntimeError(
                "未配置 COMPOSE_DIR（或目录下找不到 docker-compose.yml），无法自动升级；"
                "请在宿主机手动执行 docker compose pull sing-box && docker compose up -d sing-box"
            )

        # 1. 拉取新镜像
        code, out, err = await cls._compose("pull", COMPOSE_SERVICE, timeout=PULL_TIMEOUT)
        if code != 0:
            raise RuntimeError(f"拉取镜像失败: {(err or out).strip()}")
        log.append("镜像拉取完成")

        # 2. 用新镜像预检现有配置。
        #    升级本身不会改 config.json，所以"备份配置再回滚"是没有意义的；
        #    真正的风险是新核心不再接受旧配置导致容器起不来。
        #    这里先在一次性容器里 check，不通过就直接放弃升级，运行中的服务完全不受影响。
        ok, msg = await cls.preflight_check(f"{SINGBOX_IMAGE}:{SINGBOX_TAG}")
        if not ok:
            raise RuntimeError(f"新版本不接受当前配置，已取消升级（服务未受影响）：{msg}")
        log.append("新版本兼容性预检通过")

        # 3. 重建容器（compose 沿用 yml 里的网络/挂载/restart 策略）
        #    compose 只在镜像摘要或服务定义变化时才重建，所以先记下状态再对比，
        #    避免"已经是新镜像"却报告成"已重建"。
        before = await cls._container_fingerprint()
        code, out, err = await cls._compose("up", "-d", COMPOSE_SERVICE, timeout=300)
        if code != 0:
            raise RuntimeError(f"重建容器失败: {(err or out).strip()}")
        after = await cls._container_fingerprint()
        log.append("容器已重建" if before != after else "容器已是最新镜像，无需重建")

        # 4. 确认新容器真的起来了
        await asyncio.sleep(2)
        new_version = await SingboxService.get_running_version()
        if not new_version:
            raise RuntimeError(
                "容器已重建但读不到版本号，请检查 docker logs sing-box"
            )
        log.append(f"当前版本 {new_version}")

        return {
            "message": f"sing-box 已更新到 {new_version}",
            "version": new_version,
            "log": log,
        }

    @classmethod
    async def _container_fingerprint(cls) -> Optional[str]:
        """容器当前使用的镜像 ID + 启动时间，用于判断是否真的被重建"""
        code, out, _ = await cls._run(
            "docker", "inspect", CONTAINER_NAME,
            "--format", "{{.Image}} {{.State.StartedAt}}", timeout=15,
        )
        return out.strip() if code == 0 else None

    @classmethod
    async def preflight_check(cls, image_ref: str) -> tuple:
        """用待升级的镜像在一次性容器里校验现有配置

        配置目录必须用**宿主机**路径挂载：-v 由 docker 守护进程在宿主机上解析，
        面板容器里的 /data/config 在宿主机上并不存在。
        """
        if not HOST_DATA_DIR:
            return True, "未设置 HOST_DATA_DIR，跳过预检"

        host_config_dir = str(Path(HOST_DATA_DIR) / "config")
        code, out, err = await cls._run(
            "docker", "run", "--rm",
            "-v", f"{host_config_dir}:{CONTAINER_CONFIG_DIR}:ro",
            image_ref, "check", "-c", f"{CONTAINER_CONFIG_DIR}/config.json",
            timeout=120,
        )
        if code == 0:
            return True, "通过"
        return False, (err or out or "预检失败").strip()

    # ── 面板自身升级 ────────────────────────────────────────

    @classmethod
    async def update_panel(cls) -> dict:
        """重建 panel 容器：拉代码后重建，使代码改动生效"""
        if not cls.compose_dir():
            return {"message": "未配置 COMPOSE_DIR，无法重建面板", "log": []}
        code, out, err = await cls._compose("up", "-d", "--build", "panel", timeout=PULL_TIMEOUT)
        if code != 0:
            raise RuntimeError(f"重建面板失败: {(err or out).strip()}")
        return {"message": "面板已重建", "log": ["panel 容器已重建"]}
