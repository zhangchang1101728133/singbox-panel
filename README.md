<div align="center">

# sing-box 管理面板

**基于 Vue 3 + FastAPI 的 sing-box 服务端管理面板**

节点与订阅管理 · 一键配置 · 扫码导入 · 核心一键升级

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Vue](https://img.shields.io/badge/Vue-3-42b883?logo=vuedotjs&logoColor=white)](https://vuejs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![sing-box](https://img.shields.io/badge/sing--box-1.14-1e90ff)](https://sing-box.sagernet.org)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Docker-lightgrey)](#)

</div>

---

## ✨ 特性

| | 说明 |
|---|---|
| 🎛 **协议注册表** | 8 种协议集中在 `services/protocols.py` 一处维护，新增协议只改这一个文件，配置生成 / 一键配置 / 前端表单自动同步 |
| 🛡 **写库前校验** | 保存节点前先用 `sing-box check` 跑一遍待生成的完整配置，**不合法直接拒绝写库**，不会把服务改坏 |
| 🔄 **核心一键升级** | 面板内直接升级 sing-box：拉镜像 → **用新镜像预检现有配置** → 重建容器 → 确认版本；不兼容就取消升级，运行中的服务完全不受影响 |
| 🧠 **版本感知** | 根据当前运行的 sing-box 版本自动判断协议可用性，版本不够的协议（如 Snell 需 1.14.0+）自动隐藏，不会生成核心起不来的配置 |
| 📦 **单容器部署** | 多阶段构建：node 编译前端 → FastAPI 直接托管静态文件，生产只需一个 Python 容器，不需要 nginx |
| 📱 **移动端适配** | 响应式布局，亮/暗主题，弹窗在软键盘弹出时自适应上移 |

## 📡 支持协议

**VLESS+Reality** · **VMess** · **Shadowsocks** · **Hysteria2** · **Trojan** · **TUIC** · **AnyTLS** · **Snell**

| 协议 | 最低版本 | 说明 |
|---|---|---|
| VLESS | — | 默认 Reality + `xtls-rprx-vision` |
| VMess | — | 支持 ws / httpupgrade / http / quic 传输，可选 TLS |
| Shadowsocks | — | 默认 `2022-blake3-aes-128-gcm` |
| Hysteria2 | — | 支持 salamander 混淆与带宽限制 |
| Trojan | — | 自签证书 + TLS |
| TUIC | — | BBR 拥塞控制 |
| AnyTLS | 1.12.0 | |
| Snell | 1.14.0 | sing-box 1.14 新增 |

> 版本不够的协议会在面板里自动隐藏，不会生成 sing-box 起不来的配置。协议清单由后端 `services/protocols.py` 统一维护。

## 🚀 快速开始

### 生产部署（单容器）

```bash
git clone https://github.com/zhangchang1101728133/singbox-panel.git
cd singbox-panel
cp .env.example .env          # 首次：复制并按需修改
docker compose up -d --build
```

访问 `http://<服务器IP>:8080`，默认账号 `admin / admin123`。

> [!WARNING]
> 首次登录后请立刻修改管理员密码，且不要把 8080 端口无防护地暴露在公网 —— 面板挂载了 `/var/run/docker.sock`，等同于宿主机 root 权限。

### 开发模式（前后端热更新）

```bash
docker compose -f docker-compose.dev.yml up
```

访问 `http://<服务器IP>:5173`：

- 改 `frontend/src/**/*.vue` → Vite HMR 秒刷新
- 改 `backend/app/**/*.py` → uvicorn `--reload` 自动重启
- Vite 把 `/auth`、`/nodes`、`/sub`、`/api` 代理到后端 `:8080`

开发模式跑三个容器：`panel-backend-dev`(8080)、`panel-frontend-dev`(5173)、`sing-box`。

## ⚙️ 配置项（.env）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `SECRET_KEY` | JWT 签名密钥，**生产务必改成随机值** | `change-me-in-production` |
| `ADMIN_USER` | 管理员用户名 | `admin` |
| `ADMIN_PASS` | 管理员密码，**首次启动后写入数据库，之后改 .env 不再生效** | `admin123` |
| `SERVER_IP` | 公网 IP（拼订阅链接用），`auto` 则自动探测 | `auto` |
| `SINGBOX_TAG` | sing-box 镜像标签，`latest` 或固定版本（如 `v1.14.0`） | `latest` |
| `PROJECT_DIR` | **项目在宿主机上的绝对路径，必须设置** | — |

生成随机密钥：`openssl rand -hex 32`

> [!IMPORTANT]
> `ADMIN_PASS` 只在数据库首次初始化时生效。已经跑过一次后再改 `.env` 不会改密码 —— 要改密码得改数据库，或删掉 `data/db/singbox.db` 重新初始化（会清空所有数据）。

> [!IMPORTANT]
> `PROJECT_DIR` 必须填项目在宿主机上的绝对路径（如 `/opt/singbox-panel`）。面板要在容器里执行 `docker compose` 来升级 sing-box，而 bind 挂载的路径是由 docker 守护进程在**宿主机**上解析的 —— 填错或漏填会导致挂载到空目录，sing-box 读不到 `config.json` 直接起不来。

## 🧩 功能

- **节点管理**：增删改、启用/禁用开关，8 种协议各自的表单字段，UUID/密码一键生成
- **订阅管理**：创建/编辑/删除，自定义链接别名(slug)，按需选节点（不选=全部），一键复制订阅链接，扫码导入（二维码弹窗）
- **一键配置**：填服务器地址即生成全部 8 协议节点 + 默认订阅 + Reality 密钥
- **导出配置**：所有节点和订阅导出为 JSON
- **sing-box 管理**：检查版本、一键更新到最新

## 🎨 界面

- **顶部统计概览**：节点数 / 启用数 / 订阅数大数字卡，数字滚动计数、悬浮发光
- **亮/暗主题**：顶栏一键切换，偏好记忆在浏览器本地（localStorage）
- **可折叠卡片**：点击节点 / 订阅的标题栏即可展开或收起列表
- **节点列表**：协议彩色缩写标签（VL/VM/SS/HY2/TJ/TU/ATLS/SN），启用节点带呼吸状态点和左侧霓虹竖条
- **图标按钮**：复制 / 二维码 / 编辑 / 删除 / 登出等用 Naive UI 圆形按钮 + 内联 SVG 图标，跨平台一致、跟随主题色
- **快捷操作**：响应式网格，手机每行 2 个、宽屏一排平铺
- **动效**：品牌标题流光、背景缓慢流动、卡片入场、登录页粒子背景、按钮点击波纹
- **移动端适配**：响应式布局，列表项内容自动截断、操作按钮不溢出；弹窗默认居中、不自动聚焦输入框，软键盘弹出时自适应上移避免遮挡

## 🔀 数据流

```
浏览器 → panel(FastAPI) → 写 SQLite
                        → 生成 data/config/config.json（服务端配置）
                        → 生成 data/sub/sub_N.json（客户端订阅）
                        → docker restart sing-box（重载配置）
```

客户端拉订阅：`http://<IP>:8080/sub/download/<slug或token>`

## 📁 目录结构

```
singbox-panel/
├── docker-compose.yml        # 生产：单容器 panel + sing-box
├── docker-compose.dev.yml    # 开发：前后端都热更新
├── .env.example              # 环境变量模板（复制为 .env）
├── data/                     # 持久化数据（已 gitignore，含密钥）
│   ├── db/singbox.db
│   ├── sub/                  # 生成的订阅文件
│   └── config/               # sing-box 服务端配置 + 证书
├── backend/
│   ├── Dockerfile            # 多阶段：node 构建 dist → python 托管
│   ├── Dockerfile.dev        # uvicorn --reload
│   ├── requirements.txt
│   └── app/
│       ├── main.py           # JSON API + 托管前端 dist + SPA fallback
│       ├── models/database.py
│       ├── services/
│       │   ├── protocols.py  # 协议注册表（inbound/outbound/defaults）
│       │   ├── singbox.py    # 配置生成 + 容器控制 + 校验
│       │   └── updater.py    # 核心升级 / 面板重建
│       └── routers/          # auth / nodes / subscription / api
└── frontend/
    ├── Dockerfile.dev        # vite HMR
    ├── vite.config.js        # dev 代理 → backend:8080
    └── src/{views,components,api,stores,router}
```

## 🛠 维护

```bash
# 查看日志
docker compose logs -f panel
docker compose logs -f sing-box

# 重启 / 更新代码后重建
docker compose up -d --build

# 停止
docker compose down

# 备份数据（数据库 + 订阅 + 证书全在 data/）
tar czf backup-$(date +%F).tar.gz data/
```

## ⚠️ 注意事项

- **Reality 伪装域名必须支持 TLS 1.3**。Reality 强依赖 TLS 1.3，选到不支持的域名（如 `www.baidu.com`、`www.qq.com`）会表现为「服务端把客户端判为探测流量、回落到真实站点」，客户端只报 `reality verification failed`，极难排查。默认值 `www.taobao.com` 已实测 TLS1.3 + h2 且握手稳定。
- **容器名是写死的**：后端通过 `docker restart sing-box`、`docker exec sing-box ...` 控制代理核心，sing-box 容器名**必须叫 `sing-box`**。改 compose 里的 `container_name` 会让重启、检查更新、一键配置全部失效。
- **构建上下文**：生产 `backend/Dockerfile` 是多阶段，`COPY backend/...` 和 `COPY frontend/...` 需要项目根做 context。compose 里已设 `context: .` + `dockerfile: backend/Dockerfile`，不要改成 `./backend`。
- **host 网络**：panel 和 sing-box 都用 `network_mode: host`，重启时代理会短暂中断几秒。
- **docker.sock 挂载**：面板通过 `/var/run/docker.sock` 控制 sing-box 容器，等同于宿主机 root 权限。请务必改掉默认密码，并避免把面板直接暴露在公网。
- **构建资源**：`docker compose up -d --build` 会在本机编译前端（`npm install` + `vite`），瞬时吃满 CPU 和内存。2 核 / 2G 的小机器务必先配 swap（建议 4G），否则构建期间内存耗尽会拖垮整机、连带 sing-box 和面板失联。内存紧张时也可在别处构建镜像，服务器只跑 `docker compose up -d`（不带 `--build`）。

## 📮 联系我

- **QQ：`1101728133`**
- 邮箱：1101728133@qq.com
- 问题反馈：[GitHub Issues](https://github.com/zhangchang1101728133/singbox-panel/issues)

## 📄 开源协议

本项目基于 [MIT License](LICENSE) 开源。
