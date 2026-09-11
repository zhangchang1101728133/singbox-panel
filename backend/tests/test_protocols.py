"""protocols.py 单元测试

纯逻辑测试，不需要 sing-box 二进制：验证各协议生成的 inbound / outbound 结构，
以及几个**真实踩过的坑**（Reality 不能带证书、QUIC 不能带 uTLS、SS2022 密钥长度），
避免以后重构时又把它们改回去。
"""
import base64

import pytest

from app.services import protocols

ALL_PROTOCOLS = sorted(protocols.PROTOCOLS)

# QUIC 传输的协议：sing-box 的 QUIC 栈不支持 uTLS
QUIC_PROTOCOLS = {"hysteria2", "tuic"}

# Reality 节点配置（结构对齐一键配置生成的内容）
#
# ⚠️ 下面全部是**一次性生成的假凭据**，不对应任何真实部署。
#    千万不要把生产环境的密钥粘贴到这里：本仓库是公开的，密钥一旦提交
#    就等于公开（而且 git 历史里会留下副本，删掉文件也删不干净）。
REALITY_CONFIG = {
    "uuid": "11111111-1111-1111-1111-111111111111",
    "flow": "xtls-rprx-vision",
    "tls": {
        "enabled": True,
        "server_name": protocols.DEFAULT_REALITY_SNI,
        "reality": {
            "enabled": True,
            "public_key": "BbjvpAGI8BbcPOLyptfaRGsDcBFRgdZVoHgZFtXskRk",
            "private_key": "qOPBcBP2Q7BIoIfT3MftJiwIGM4mDaPaIydAPtnepX8",
            "short_id": "0123456789abcdef",
        },
    },
}


def make_node(protocol_id, config=None, port=12345):
    """构造一个节点 dict（结构与数据库行一致）"""
    return {
        "id": 1,
        "name": protocol_id,
        "type": protocol_id,
        "server": "example.com",
        "server_port": port,
        "enabled": True,
        "config": protocols.default_config(protocol_id) if config is None else config,
    }


# ── 注册表一致性 ────────────────────────────────────────────

class TestRegistry:
    def test_registry_keys_match_declared_type(self):
        """注册表的 key 必须和协议生成出来的 type 一致"""
        for pid in ALL_PROTOCOLS:
            node = make_node(pid)
            assert protocols.build_inbound(node)["type"] == pid, f"{pid} inbound type 不一致"
            assert protocols.build_outbound(node)["type"] == pid, f"{pid} outbound type 不一致"

    def test_every_protocol_has_required_metadata(self):
        for pid, proto in protocols.PROTOCOLS.items():
            assert proto.get("label"), f"{pid} 缺 label"
            assert isinstance(proto.get("default_port"), int), f"{pid} 缺 default_port"
            assert isinstance(proto.get("fields"), list) and proto["fields"], f"{pid} 缺 fields"
            for fn in ("inbound", "outbound", "defaults"):
                assert callable(proto.get(fn)), f"{pid} 的 {fn} 不可调用"

    def test_default_ports_are_unique(self):
        ports = [p["default_port"] for p in protocols.PROTOCOLS.values()]
        assert len(ports) == len(set(ports)), "存在重复的默认端口"

    def test_every_protocol_has_unique_short_abbr(self):
        """缩写由后端注册表统一提供，前端不再自己维护一份"""
        abbrs = []
        for pid, proto in protocols.PROTOCOLS.items():
            abbr = proto.get("abbr")
            assert abbr, f"{pid} 缺 abbr"
            assert 1 <= len(abbr) <= 4, f"{pid} 的 abbr 过长: {abbr}"
            abbrs.append(abbr)
        assert len(abbrs) == len(set(abbrs)), "存在重复的协议缩写"

    def test_protocol_list_exposes_abbr(self):
        for item in protocols.protocol_list("1.14.0"):
            assert item["abbr"] == protocols.PROTOCOLS[item["id"]]["abbr"]

    def test_field_keys_are_unique_per_protocol(self):
        for pid, proto in protocols.PROTOCOLS.items():
            keys = [f["key"] for f in proto["fields"]]
            assert len(keys) == len(set(keys)), f"{pid} 有重复字段"


# ── 每个协议都能生成合法结构 ────────────────────────────────

class TestBuildOutput:
    @pytest.mark.parametrize("pid", ALL_PROTOCOLS)
    def test_inbound_has_no_common_fields(self, pid):
        """inbound 不含 tag/listen/listen_port —— 这些由调用方补全，避免双份真相"""
        inbound = protocols.build_inbound(make_node(pid))
        for key in ("tag", "listen", "listen_port"):
            assert key not in inbound, f"{pid} inbound 不应包含 {key}"

    @pytest.mark.parametrize("pid", ALL_PROTOCOLS)
    def test_outbound_carries_server(self, pid):
        out = protocols.build_outbound(make_node(pid, port=45678))
        assert out["server"] == "example.com"
        assert out["server_port"] == 45678

    @pytest.mark.parametrize("pid", ALL_PROTOCOLS)
    def test_defaults_are_json_serializable(self, pid):
        import json
        cfg = protocols.default_config(pid)
        json.dumps(cfg)  # 不抛异常即可

    @pytest.mark.parametrize("pid", ALL_PROTOCOLS)
    def test_empty_config_does_not_crash(self, pid):
        """配置为空时也不能抛异常（用户可能刚打开表单就点保存）"""
        node = make_node(pid, config={})
        protocols.build_inbound(node)
        protocols.build_outbound(node)


# ── 回归测试：真实踩过的坑 ──────────────────────────────────

class TestRealityInvariants:
    """Reality 的约束：服务端不能带证书，客户端必须要 uTLS"""

    def test_inbound_omits_certificate(self):
        # sing-box 会直接报 `certificate is unavailable in reality` 起不来
        inbound = protocols.build_inbound(make_node("vless", REALITY_CONFIG))
        tls = inbound["tls"]
        assert "certificate_path" not in tls
        assert "key_path" not in tls
        assert tls["reality"]["enabled"] is True
        assert tls["reality"]["private_key"] == REALITY_CONFIG["tls"]["reality"]["private_key"]

    def test_inbound_handshake_target_follows_server_name(self):
        """伪装域名同时作为握手目标，两者必须一致，否则 Reality 静默失效"""
        inbound = protocols.build_inbound(make_node("vless", REALITY_CONFIG))
        reality = inbound["tls"]["reality"]
        assert reality["handshake"]["server"] == protocols.DEFAULT_REALITY_SNI
        assert inbound["tls"]["server_name"] == protocols.DEFAULT_REALITY_SNI

    def test_outbound_keeps_utls(self):
        # sing-box 对 Reality 客户端要求 uTLS，去掉会报 uTLS is required by reality client
        out = protocols.build_outbound(make_node("vless", REALITY_CONFIG))
        assert out["tls"]["utls"]["enabled"] is True
        assert out["tls"]["reality"]["public_key"] == REALITY_CONFIG["tls"]["reality"]["public_key"]

    def test_non_reality_vless_still_uses_certificate(self):
        """没有开 Reality 时应当走自签证书，而不是被误判成 Reality"""
        inbound = protocols.build_inbound(make_node("vless"))
        assert not (inbound["tls"].get("reality") or {}).get("enabled")
        assert inbound["tls"]["certificate_path"] == protocols.CERT_PATH


class TestUtlsQuicConflict:
    """QUIC 传输不支持 uTLS，带上会直接报 unsupported usage for uTLS"""

    @pytest.mark.parametrize("pid", sorted(QUIC_PROTOCOLS))
    def test_quic_outbound_has_no_utls(self, pid):
        out = protocols.build_outbound(make_node(pid))
        assert "utls" not in (out.get("tls") or {}), f"{pid} 不应带 utls"

    @pytest.mark.parametrize("pid", sorted(set(ALL_PROTOCOLS) - QUIC_PROTOCOLS))
    def test_non_quic_tls_outbound_keeps_utls(self, pid):
        """非 QUIC 协议只要用了 TLS，就应当带 uTLS 指纹"""
        tls = protocols.build_outbound(make_node(pid)).get("tls")
        if not tls:
            pytest.skip(f"{pid} 默认不使用 TLS")
        assert tls["utls"]["enabled"] is True


class TestSnellVersionPair:
    """服务端 version 5 对应客户端 version 4（v5 仅服务端形态，线路同 v4）"""

    def test_inbound_uses_server_version(self):
        assert protocols.build_inbound(make_node("snell"))["version"] == 5

    def test_outbound_downgrades_to_v4(self):
        cfg = protocols.default_config("snell")
        out = protocols.build_outbound(make_node("snell", cfg))
        assert out["version"] == 4
        assert out["psk"] == cfg["psk"]


class TestShadowsocksKeys:
    """SS2022 的密码必须是 base64(定长随机字节)，长度错会在启动时报 bad key"""

    def test_generated_password_matches_method_key_length(self):
        for method, key_len in protocols.SS_KEY_LENGTH.items():
            raw = base64.b64decode(protocols.gen_ss_password(method))
            assert len(raw) == key_len, f"{method} 密钥长度应为 {key_len}"

    def test_random_value_uses_method_specific_length(self):
        method = "2022-blake3-aes-256-gcm"
        value = protocols.random_value("shadowsocks", "password", {"method": method})
        assert len(base64.b64decode(value)) == protocols.SS_KEY_LENGTH[method]

    def test_legacy_method_falls_back_to_plain_password(self):
        value = protocols.random_value("shadowsocks", "password", {"method": "aes-128-gcm"})
        assert len(value) == 20  # gen_pass 默认长度

    def test_password_is_not_reused(self):
        assert protocols.gen_ss_password() != protocols.gen_ss_password()


class TestUuidAndPasswordGenerators:
    def test_uuid_is_valid_v4(self):
        import uuid as uuid_mod
        for _ in range(5):
            parsed = uuid_mod.UUID(protocols.gen_uuid())
            assert parsed.version == 4

    def test_random_value_generates_uuid_for_uuid_fields(self):
        import uuid as uuid_mod
        uuid_mod.UUID(protocols.random_value("vmess", "uuid"))


# ── 版本门控 ────────────────────────────────────────────────

class TestVersionGating:
    @pytest.mark.parametrize("raw,expected", [
        ("1.14.0", (1, 14, 0)),
        ("v1.12.3", (1, 12, 3)),
        ("1.13.19", (1, 13, 19)),
        ("1.14.0-beta.2", (1, 14, 0)),
        ("", (0,)),
        ("garbage", (0,)),
    ])
    def test_version_tuple(self, raw, expected):
        assert protocols.version_tuple(raw) == expected

    def test_snell_requires_114(self):
        assert protocols.is_supported("snell", "1.13.19") is False
        assert protocols.is_supported("snell", "1.14.0") is True

    def test_anytls_requires_112(self):
        assert protocols.is_supported("anytls", "1.11.0") is False
        assert protocols.is_supported("anytls", "1.12.0") is True

    def test_protocols_without_min_version_always_available(self):
        for pid in ("vless", "vmess", "shadowsocks", "trojan", "tuic", "hysteria2"):
            assert protocols.is_supported(pid, "1.0.0") is True

    def test_unknown_protocol_is_not_supported(self):
        assert protocols.is_supported("nonexistent", "1.14.0") is False

    def test_missing_core_version_does_not_hide_protocols(self):
        """探测不到版本时不应把协议全藏起来"""
        assert protocols.is_supported("snell", None) is True

    def test_protocol_list_marks_availability(self):
        items = {i["id"]: i for i in protocols.protocol_list("1.13.19")}
        assert set(items) == set(protocols.PROTOCOLS)
        assert items["snell"]["available"] is False
        assert items["anytls"]["available"] is True
        assert items["vless"]["available"] is True


def test_all_eight_protocols_registered():
    """协议清单是产品承诺的一部分，数量变化时应当显式确认"""
    assert set(protocols.PROTOCOLS) == {
        "vless", "vmess", "shadowsocks", "hysteria2",
        "trojan", "tuic", "anytls", "snell",
    }
