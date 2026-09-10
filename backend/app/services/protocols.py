"""sing-box 协议注册表

这里是一个协议（inbound / outbound）的唯一数据源。
新增或下线协议只需要改这个文件：配置生成、一键配置、前端表单都从这里读取。

每个协议描述：
    id            sing-box 的 type 值
    label         显示名
    min_version   该协议可用的最低 sing-box 版本（None 表示一直可用）
    default_port  一键配置/新建节点时的默认端口
    fields        前端表单需要渲染的字段
    inbound()     生成服务端 inbound
    outbound()    生成客户端 outbound
    defaults()    一键配置时的默认 config
"""
import base64
import secrets
import uuid as uuid_mod

# TLS 入站使用的证书（由 sing-box 容器只读挂载 /etc/sing-box）
CERT_PATH = "/etc/sing-box/cert.pem"
KEY_PATH = "/etc/sing-box/key.pem"

# 客户端订阅里 TUN 之外的默认伪装指纹
UTLS_FINGERPRINT = "chrome"

# Reality 默认伪装域名。
#
# 选域名的硬性条件（换之前务必逐条确认，否则 Reality 会静默失效）：
#   1. 必须支持 TLS 1.3 —— Reality 的硬要求。www.baidu.com / www.qq.com 都不支持，
#      用了会出现「服务端把客户端判为探测流量、回落到真实站点」，客户端只报
#      reality verification failed，排查成本很高。
#   2. 不能被墙 —— SNI 被墙会导致连接直接被阻断。
#   3. 本机（代理服务器）能正常握手到它，且延迟低且稳定：Reality 服务端要拿它的
#      证书，握手 RTT 会计入连接建立耗时。
#   4. 最好支持 h2，让 ClientHello 更接近真实浏览器。
#
# www.taobao.com 实测：TLS1.3 + h2，握手 3ms、抖动 2ms，国内超级大站绝不被墙。
DEFAULT_REALITY_SNI = "www.taobao.com"

# 2022 系列为 sing-box 推荐的 Shadowsocks 加密方式
SS_METHODS = [
    "2022-blake3-aes-128-gcm",
    "2022-blake3-chacha20-poly1305",
    "2022-blake3-aes-256-gcm",
    "chacha20-ietf-poly1305",
    "aes-128-gcm",
    "aes-256-gcm",
    "none",
]

# 2022 系列的密码不是任意字符串，而是 base64(随机 N 字节)；长度不匹配会在启动时报 bad key
SS_KEY_LENGTH = {
    "2022-blake3-aes-128-gcm": 16,
    "2022-blake3-chacha20-poly1305": 32,
    "2022-blake3-aes-256-gcm": 32,
}

# sing-box 支持的 V2Ray 传输层。
# 注意：gRPC 传输在官方镜像里没有 with_standard_grpc 标签，走的是性能较差的内置实现，
# 因此这里只暴露官方镜像验证过的四种。
TRANSPORT_TYPES = ["ws", "httpupgrade", "http", "quic"]

TUIC_CONGESTION = ["cubic", "new_reno", "bbr"]

HY2_OBFS_TYPES = ["", "salamander"]


def gen_uuid() -> str:
    return str(uuid_mod.uuid4())


def gen_pass(length: int = 20) -> str:
    return secrets.token_urlsafe(length)[:length]


def gen_ss_password(method: str = "") -> str:
    """Shadowsocks 密码：2022 系列必须是 base64(定长随机字节)，其余用普通口令"""
    key_len = SS_KEY_LENGTH.get(method or SS_METHODS[0])
    if key_len:
        return base64.b64encode(secrets.token_bytes(key_len)).decode()
    return gen_pass()


def _tls_inbound(server_name: str = "", alpn=None, reality=None) -> dict:
    """服务端 TLS：自签证书路径 + 可选的 ALPN / Reality

    Reality 入站不能同时指定 certificate_path / key_path —— sing-box 会直接报
    `certificate is unavailable in reality`，启动失败。
    """
    tls = {"enabled": True}
    if not reality:
        tls["certificate_path"] = CERT_PATH
        tls["key_path"] = KEY_PATH
    if server_name:
        tls["server_name"] = server_name
    if alpn:
        tls["alpn"] = alpn
    if reality:
        tls["reality"] = reality
    return tls


def _tls_outbound(server_name: str, insecure: bool = True, alpn=None, reality=None,
                  utls: bool = True) -> dict:
    """客户端 TLS。

    默认 insecure=True：面板签发的是自签证书，客户端无法校验链。
    只有当节点明确配了可信证书时才应关掉。

    utls=False 用于 QUIC 类协议（hysteria2 / tuic）：sing-box 的 QUIC 传输
    不支持 uTLS，带上会直接报 `unsupported usage for uTLS` 导致连不上。
    """
    tls = {
        "enabled": True,
        "server_name": server_name,
        "insecure": insecure,
    }
    if utls:
        tls["utls"] = {"enabled": True, "fingerprint": UTLS_FINGERPRINT}
    if alpn:
        tls["alpn"] = alpn
    if reality:
        # Reality 客户端同样需要 utls（sing-box 会报 uTLS is required by reality client）
        tls["reality"] = reality
    return tls


def _merge_transport(cfg: dict) -> dict:
    """客户端 transport：只序列化已填写的字段"""
    transport = cfg.get("transport") or {}
    if not transport.get("type"):
        return {}
    out = {"type": transport["type"]}
    for key in ("host", "path", "service_name"):
        if transport.get(key):
            out[key] = transport[key]
    return out


def _server_transport(cfg: dict) -> dict:
    """服务端 transport：与客户端保持对称"""
    transport = cfg.get("transport") or {}
    if not transport.get("type"):
        return {}
    out = {"type": transport["type"]}
    for key in ("host", "path", "service_name"):
        if transport.get(key):
            out[key] = transport[key]
    return out


# ─────────────────────────────────────────────────────────────
# VLESS
# ─────────────────────────────────────────────────────────────
def vless_inbound(node, cfg):
    tls_cfg = cfg.get("tls") or {}
    reality = tls_cfg.get("reality") or {}

    tls = {}
    if reality.get("enabled"):
        server_name = tls_cfg.get("server_name") or DEFAULT_REALITY_SNI
        tls = _tls_inbound(
            server_name=server_name,
            reality={
                "enabled": True,
                "handshake": {
                    "server": reality.get("handshake_server") or server_name,
                    "server_port": reality.get("handshake_server_port") or 443,
                },
                "private_key": reality.get("private_key", ""),
                "short_id": [reality.get("short_id", "")] if reality.get("short_id") else [],
            },
        )
    elif tls_cfg.get("enabled"):
        tls = _tls_inbound(server_name=tls_cfg.get("server_name", ""))

    inbound = {
        "type": "vless",
        "users": [{"uuid": cfg.get("uuid", "")}],
    }
    # flow 只在 TLS 下有意义，Reality 默认使用 xtls-rprx-vision
    flow = cfg.get("flow") or ("xtls-rprx-vision" if tls else "")
    if flow:
        inbound["users"][0]["flow"] = flow
    if tls:
        inbound["tls"] = tls

    transport = _server_transport(cfg)
    if transport:
        inbound["transport"] = transport
    return inbound


def vless_outbound(node, cfg):
    tls_cfg = cfg.get("tls") or {}
    reality = tls_cfg.get("reality") or {}

    out = {
        "type": "vless",
        "server": node["server"],
        "server_port": node["server_port"],
        "uuid": cfg.get("uuid", ""),
    }
    tls = {}
    if reality.get("enabled"):
        tls = _tls_outbound(
            server_name=tls_cfg.get("server_name", ""),
            insecure=False,
            reality={
                "enabled": True,
                "public_key": reality.get("public_key", ""),
                "short_id": reality.get("short_id", ""),
            },
        )
    elif tls_cfg.get("enabled"):
        tls = _tls_outbound(
            server_name=tls_cfg.get("server_name") or node["server"],
            insecure=bool(tls_cfg.get("insecure", True)),
        )

    if tls:
        out["tls"] = tls
        flow = cfg.get("flow") or ("xtls-rprx-vision" if reality.get("enabled") else "")
        if flow:
            out["flow"] = flow

    transport = _merge_transport(cfg)
    if transport:
        out["transport"] = transport
    return out


def vless_defaults(**kw):
    return {
        "uuid": gen_uuid(),
        "flow": "xtls-rprx-vision",
        "tls": {
            "enabled": True,
            "server_name": kw.get("sni", DEFAULT_REALITY_SNI),
            "reality": kw.get("reality", {}),
        },
    }


# ─────────────────────────────────────────────────────────────
# VMess
# ─────────────────────────────────────────────────────────────
def vmess_inbound(node, cfg):
    inbound = {
        "type": "vmess",
        "users": [{"uuid": cfg.get("uuid", ""), "alterId": int(cfg.get("alter_id", 0) or 0)}],
    }
    transport = _server_transport(cfg) or {"type": "ws", "path": cfg.get("path", "/vmws")}
    inbound["transport"] = transport
    tls_cfg = cfg.get("tls") or {}
    if tls_cfg.get("enabled"):
        inbound["tls"] = _tls_inbound(server_name=tls_cfg.get("server_name", ""))
    return inbound


def vmess_outbound(node, cfg):
    out = {
        "type": "vmess",
        "server": node["server"],
        "server_port": node["server_port"],
        "uuid": cfg.get("uuid", ""),
        "alter_id": int(cfg.get("alter_id", 0) or 0),
        "security": cfg.get("security", "auto"),
    }
    transport = _merge_transport(cfg) or {"type": "ws", "path": cfg.get("path", "/vmws")}
    out["transport"] = transport
    tls_cfg = cfg.get("tls") or {}
    if tls_cfg.get("enabled"):
        out["tls"] = _tls_outbound(
            server_name=tls_cfg.get("server_name") or node["server"],
            insecure=bool(tls_cfg.get("insecure", True)),
        )
    return out


def vmess_defaults(**kw):
    return {
        "uuid": gen_uuid(),
        "alter_id": 0,
        "security": "auto",
        "transport": {"type": "ws", "path": "/vmws"},
        "tls": {"enabled": False, "server_name": ""},
    }


# ─────────────────────────────────────────────────────────────
# Shadowsocks
# ─────────────────────────────────────────────────────────────
def shadowsocks_inbound(node, cfg):
    return {
        "type": "shadowsocks",
        "method": cfg.get("method") or SS_METHODS[0],
        "password": cfg.get("password", ""),
    }


def shadowsocks_outbound(node, cfg):
    return {
        "type": "shadowsocks",
        "server": node["server"],
        "server_port": node["server_port"],
        "method": cfg.get("method") or SS_METHODS[0],
        "password": cfg.get("password", ""),
    }


def shadowsocks_defaults(**kw):
    method = kw.get("method") or SS_METHODS[0]
    return {"method": method, "password": gen_ss_password(method)}


# ─────────────────────────────────────────────────────────────
# Hysteria2
# ─────────────────────────────────────────────────────────────
def _hy2_obfs(cfg):
    obfs = cfg.get("obfs") or {}
    if not obfs.get("type"):
        return None
    return {"type": obfs["type"], "password": obfs.get("password", "")}


def hysteria2_inbound(node, cfg):
    inbound = {
        "type": "hysteria2",
        "users": [{"password": cfg.get("password", "")}],
        "tls": _tls_inbound(),
    }
    obfs = _hy2_obfs(cfg)
    if obfs:
        inbound["obfs"] = obfs
    up = cfg.get("up_mbps")
    down = cfg.get("down_mbps")
    if up:
        inbound["up_mbps"] = int(up)
    if down:
        inbound["down_mbps"] = int(down)
    return inbound


def hysteria2_outbound(node, cfg):
    out = {
        "type": "hysteria2",
        "server": node["server"],
        "server_port": node["server_port"],
        "password": cfg.get("password", ""),
        "tls": _tls_outbound(
            server_name=(cfg.get("tls") or {}).get("server_name") or node["server"],
            insecure=bool((cfg.get("tls") or {}).get("insecure", True)),
            utls=False,  # QUIC 传输不支持 uTLS
        ),
    }
    obfs = _hy2_obfs(cfg)
    if obfs:
        out["obfs"] = obfs
    up = cfg.get("up_mbps")
    down = cfg.get("down_mbps")
    if up:
        out["up_mbps"] = int(up)
    if down:
        out["down_mbps"] = int(down)
    return out


def hysteria2_defaults(**kw):
    return {
        "password": gen_pass(),
        "up_mbps": 100,
        "down_mbps": 100,
        "obfs": {"type": "salamander", "password": gen_pass(16)},
        "tls": {"enabled": True, "insecure": True},
    }


# ─────────────────────────────────────────────────────────────
# Trojan / AnyTLS（同为 password + TLS，仅字段名不同）
# ─────────────────────────────────────────────────────────────
def trojan_inbound(node, cfg):
    return {
        "type": "trojan",
        "users": [{"name": "user1", "password": cfg.get("password", "")}],
        "tls": _tls_inbound(),
    }


def trojan_outbound(node, cfg):
    return {
        "type": "trojan",
        "server": node["server"],
        "server_port": node["server_port"],
        "password": cfg.get("password", ""),
        "tls": _tls_outbound(
            server_name=(cfg.get("tls") or {}).get("server_name") or node["server"],
            insecure=bool((cfg.get("tls") or {}).get("insecure", True)),
        ),
    }


def anytls_inbound(node, cfg):
    inbound = {
        "type": "anytls",
        "users": [{"name": "user1", "password": cfg.get("password", "")}],
        "tls": _tls_inbound(),
    }
    padding = cfg.get("padding_scheme")
    if padding:
        inbound["padding_scheme"] = padding
    return inbound


def anytls_outbound(node, cfg):
    out = {
        "type": "anytls",
        "server": node["server"],
        "server_port": node["server_port"],
        "password": cfg.get("password", ""),
        "tls": _tls_outbound(
            server_name=(cfg.get("tls") or {}).get("server_name") or node["server"],
            insecure=bool((cfg.get("tls") or {}).get("insecure", True)),
        ),
    }
    padding = cfg.get("padding_scheme")
    if padding:
        out["padding_scheme"] = padding
    return out


def password_defaults(**kw):
    return {"password": gen_pass(), "tls": {"enabled": True, "insecure": True}}


# ─────────────────────────────────────────────────────────────
# TUIC
# ─────────────────────────────────────────────────────────────
def tuic_inbound(node, cfg):
    return {
        "type": "tuic",
        "users": [{"uuid": cfg.get("uuid", ""), "password": cfg.get("password", "")}],
        "congestion_control": cfg.get("congestion_control") or "bbr",
        "tls": _tls_inbound(alpn=["h3"]),
    }


def tuic_outbound(node, cfg):
    return {
        "type": "tuic",
        "server": node["server"],
        "server_port": node["server_port"],
        "uuid": cfg.get("uuid", ""),
        "password": cfg.get("password", ""),
        "congestion_control": cfg.get("congestion_control") or "bbr",
        "tls": _tls_outbound(
            server_name=(cfg.get("tls") or {}).get("server_name") or node["server"],
            insecure=bool((cfg.get("tls") or {}).get("insecure", True)),
            alpn=["h3"],
            utls=False,  # QUIC 传输不支持 uTLS
        ),
    }


def tuic_defaults(**kw):
    return {
        "uuid": gen_uuid(),
        "password": gen_pass(),
        "congestion_control": "bbr",
        "tls": {"enabled": True, "insecure": True},
    }


# ─────────────────────────────────────────────────────────────
# Snell（sing-box 1.14.0 新增）
#   服务端 version 5 <-> 客户端 version 4 是一对（v5 仅服务端形态，线路同 v4）
# ─────────────────────────────────────────────────────────────
def snell_inbound(node, cfg):
    version = int(cfg.get("version", 5) or 5)
    inbound = {
        "type": "snell",
        "psk": cfg.get("psk", ""),
        "version": version,
    }
    if version >= 6:
        inbound["mode"] = cfg.get("mode") or "default"
    else:
        inbound["obfs_mode"] = cfg.get("obfs_mode") or "http"
    return inbound


def snell_outbound(node, cfg):
    version = int(cfg.get("version", 5) or 5)
    out = {
        "type": "snell",
        "server": node["server"],
        "server_port": node["server_port"],
        "psk": cfg.get("psk", ""),
        # 服务端 v5 对应客户端 v4；v6 两端一致
        "version": 4 if version == 5 else version,
    }
    if version >= 6:
        out["mode"] = cfg.get("mode") or "default"
    else:
        out["obfs_mode"] = cfg.get("obfs_mode") or "http"
        out["obfs_host"] = cfg.get("obfs_host") or "bing.com"
    return out


def snell_defaults(**kw):
    return {
        "psk": gen_pass(16),
        "version": 5,
        "obfs_mode": "http",
        "obfs_host": "bing.com",
    }


# ─────────────────────────────────────────────────────────────
# 注册表
# ─────────────────────────────────────────────────────────────
PROTOCOLS = {
    "vless": {
        "label": "VLESS + Reality",
        "min_version": None,
        "default_port": 44300,
        "inbound": vless_inbound,
        "outbound": vless_outbound,
        "defaults": vless_defaults,
        "fields": [
            {"key": "uuid", "label": "UUID", "type": "text", "gen": "uuid"},
            {"key": "tls.reality.enabled", "label": "启用 Reality", "type": "bool", "default": True},
            {"key": "tls.server_name", "label": "SNI 伪装域名", "type": "text", "default": DEFAULT_REALITY_SNI},
            {"key": "tls.reality.public_key", "label": "Reality 公钥", "type": "text"},
            {"key": "tls.reality.private_key", "label": "Reality 私钥", "type": "text"},
            {"key": "tls.reality.short_id", "label": "Short ID", "type": "text"},
        ],
    },
    "vmess": {
        "label": "VMess",
        "min_version": None,
        "default_port": 44301,
        "inbound": vmess_inbound,
        "outbound": vmess_outbound,
        "defaults": vmess_defaults,
        "fields": [
            {"key": "uuid", "label": "UUID", "type": "text", "gen": "uuid"},
            {"key": "transport.type", "label": "传输方式", "type": "select", "options": TRANSPORT_TYPES},
            {"key": "transport.path", "label": "路径", "type": "text", "default": "/vmws"},
            {"key": "transport.host", "label": "Host", "type": "text"},
            {"key": "tls.enabled", "label": "启用 TLS", "type": "bool", "default": False},
            {"key": "tls.server_name", "label": "SNI", "type": "text"},
        ],
    },
    "shadowsocks": {
        "label": "Shadowsocks",
        "min_version": None,
        "default_port": 44302,
        "inbound": shadowsocks_inbound,
        "outbound": shadowsocks_outbound,
        "defaults": shadowsocks_defaults,
        "fields": [
            {"key": "method", "label": "加密方式", "type": "select", "options": SS_METHODS},
            {"key": "password", "label": "密码", "type": "text", "gen": "password"},
        ],
    },
    "hysteria2": {
        "label": "Hysteria2",
        "min_version": None,
        "default_port": 44303,
        "inbound": hysteria2_inbound,
        "outbound": hysteria2_outbound,
        "defaults": hysteria2_defaults,
        "fields": [
            {"key": "password", "label": "密码", "type": "text", "gen": "password"},
            {"key": "obfs.type", "label": "混淆 (obfs)", "type": "select", "options": HY2_OBFS_TYPES},
            {"key": "obfs.password", "label": "混淆密码", "type": "text", "gen": "password"},
            {"key": "up_mbps", "label": "上行 Mbps", "type": "number"},
            {"key": "down_mbps", "label": "下行 Mbps", "type": "number"},
        ],
    },
    "trojan": {
        "label": "Trojan",
        "min_version": None,
        "default_port": 44304,
        "inbound": trojan_inbound,
        "outbound": trojan_outbound,
        "defaults": password_defaults,
        "fields": [
            {"key": "password", "label": "密码", "type": "text", "gen": "password"},
        ],
    },
    "tuic": {
        "label": "TUIC",
        "min_version": None,
        "default_port": 44305,
        "inbound": tuic_inbound,
        "outbound": tuic_outbound,
        "defaults": tuic_defaults,
        "fields": [
            {"key": "uuid", "label": "UUID", "type": "text", "gen": "uuid"},
            {"key": "password", "label": "密码", "type": "text", "gen": "password"},
            {"key": "congestion_control", "label": "拥塞控制", "type": "select", "options": TUIC_CONGESTION},
        ],
    },
    "anytls": {
        "label": "AnyTLS",
        "min_version": "1.12.0",
        "default_port": 44306,
        "inbound": anytls_inbound,
        "outbound": anytls_outbound,
        "defaults": password_defaults,
        "fields": [
            {"key": "password", "label": "密码", "type": "text", "gen": "password"},
        ],
    },
    "snell": {
        "label": "Snell",
        "min_version": "1.14.0",
        "default_port": 44307,
        "inbound": snell_inbound,
        "outbound": snell_outbound,
        "defaults": snell_defaults,
        "fields": [
            {"key": "psk", "label": "PSK 预共享密钥", "type": "text", "gen": "password"},
            {"key": "version", "label": "版本", "type": "select", "options": ["5", "6"]},
            {"key": "obfs_mode", "label": "HTTP 混淆", "type": "select", "options": ["http", "none"]},
            {"key": "obfs_host", "label": "混淆 Host", "type": "text", "default": "bing.com"},
        ],
    },
}


def get_protocol(protocol_id: str) -> dict:
    return PROTOCOLS.get(protocol_id)


def supported_ids() -> set:
    return set(PROTOCOLS)


def version_tuple(version: str):
    """'1.13.19' -> (1, 13, 19)；无法解析时返回 (0,)"""
    if not version:
        return (0,)
    parts = []
    for chunk in str(version).split("-")[0].split(".")[:3]:
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def is_supported(protocol_id: str, core_version: str = None) -> bool:
    """协议是否被当前 sing-box 核心支持"""
    proto = PROTOCOLS.get(protocol_id)
    if not proto:
        return False
    min_version = proto.get("min_version")
    if not min_version or not core_version:
        return True
    return version_tuple(core_version) >= version_tuple(min_version)


def protocol_list(core_version: str = None) -> list:
    """给前端的协议清单，带 available 标记"""
    items = []
    for pid, proto in PROTOCOLS.items():
        available = is_supported(pid, core_version)
        items.append({
            "id": pid,
            "label": proto["label"],
            "default_port": proto["default_port"],
            "min_version": proto.get("min_version"),
            "available": available,
            "fields": proto["fields"],
        })
    return items


def build_inbound(node: dict) -> dict:
    proto = PROTOCOLS.get(node["type"])
    cfg = node.get("config") or {}
    inbound = proto["inbound"](node, cfg)
    # 公共字段由调用方补全（tag / listen / listen_port）
    return inbound


def build_outbound(node: dict) -> dict:
    proto = PROTOCOLS.get(node["type"])
    cfg = node.get("config") or {}
    outbound = proto["outbound"](node, cfg)
    outbound.setdefault("type", node["type"])
    return outbound


def default_config(protocol_id: str, **kw) -> dict:
    proto = PROTOCOLS.get(protocol_id)
    return proto["defaults"](**kw) if proto else {}


def random_value(protocol_id: str, field_key: str, config: dict = None) -> str:
    """为表单里的「生成」按钮产生合法随机值

    Shadowsocks 2022 的密码格式取决于当前选择的加密方式，所以密钥规则放在这里，
    前端不重复实现。
    """
    config = config or {}
    if protocol_id == "shadowsocks" and field_key == "password":
        return gen_ss_password(config.get("method") or SS_METHODS[0])
    if field_key.endswith("uuid"):
        return gen_uuid()
    return gen_pass()
