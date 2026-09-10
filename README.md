# sing-box 管理面板

基于 Vue 3 + FastAPI 的 sing-box 服务端管理面板：节点与订阅管理、一键配置、扫码导入，亮/暗主题与移动端适配。

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | Vue 3 + Naive UI + Pinia + Vue Router + Vite |
| 后端 | FastAPI（纯 JSON API）+ aiosqlite |
| 部署 | Docker Compose（生产单容器 / 开发前后端热更新） |
| 代理核心 | sing-box 官方镜像（host 网络） |

## 支持协议

VLESS+Reality · VMess · Shadowsocks · Hysteria2 · Trojan · TUIC · AnyTLS · Snell

协议清单由后端 `services/protocols.py` 统一维护，并根据**当前运行的 sing-box 版本**自动判断可用性：
低于要求版本的协议（如 Snell 需 1.14.0+）会在面板里自动隐藏，不会生成 sing-box 起不来的配置。

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

## 目录结构

```
singbox-panel/
├── docker-compose.yml        # 生产：单容器 panel + sing-box
├── docker-compose.dev.yml    # 开发：前后端都热更新
├── .env                      # 环境变量（密钥/管理员/IP）
├── data/                     # 持久化数据（数据库 + 订阅 + 证书）
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
│       ├── services/singbox.py   # 配置生成 + 容器控制
│       └── routers/          # auth / nodes / subscription / api
└── frontend/
    ├── Dockerfile.dev        # vite HMR
    ├── vite.config.js        # dev 代理 → backend:8080
    └── src/{views,components,api,stores,router}
```

## 快速开始

### 生产部署（单容器）

```bash
cd /opt/singbox-panel
cp .env.example .env          # 首次：复制并修改配置
docker compose up -d --build
```

访问 `http://<服务器IP>:8080`，默认账号 `admin / admin123`。

生产镜像是多阶段构建：先用 node 把前端编译成静态文件，再由 FastAPI 直接托管，最终只有一个 Python 容器，无需 nginx。

### 开发模式（前后端热更新）

```bash
cd /opt/singbox-panel
docker compose -f docker-compose.dev.yml up
```

访问 `http://<服务器IP>:5173`：

- 改 `frontend/src/**/*.vue` → Vite HMR 秒刷新
- 改 `backend/app/**/*.py` → uvicorn `--reload` 自动重启
- Vite 把 `/auth /nodes /sub /api` 代理到后端 `:8080`

开发模式跑三个容器：`panel-backend-dev`(8080)、`panel-frontend-dev`(5173)、`sing-box`。

## 配置（.env）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `SECRET_KEY` | JWT 签名密钥，**生产务必改成随机值** | `change-me-in-production` |
| `ADMIN_USER` | 管理员用户名 | `admin` |
| `ADMIN_PASS` | 管理员密码，**首次启动后写入数据库，之后改 .env 不再生效** | `admin123` |
| `SERVER_IP` | 公网 IP（拼订阅链接用），`auto` 则自动探测 | `auto` |

生成随机密钥：`openssl rand -hex 32`

> ⚠️ `ADMIN_PASS` 只在数据库首次初始化时生效。已经跑过一次后再改 `.env` 不会改密码——要改密码得改数据库，或删掉 `data/db/singbox.db` 重新初始化（会清空所有数据）。

## 功能

- **节点管理**：增删改、启用/禁用开关，7 种协议各自的表单字段，UUID/密码一键生成
- **订阅管理**：创建/编辑/删除，自定义链接别名(slug)，按需选节点（不选=全部），一键复制订阅链接，扫码导入（二维码弹窗）
- **一键配置**：填服务器地址即生成全部 7 协议节点 + 默认订阅 + Reality 密钥
- **导出配置**：所有节点和订阅导出为 JSON
- **sing-box 管理**：检查版本、一键更新到最新

## 界面

- **顶部统计概览**：节点数 / 启用数 / 订阅数大数字卡，数字滚动计数、悬浮发光
- **亮/暗主题**：顶栏一键切换，偏好记忆在浏览器本地（localStorage）
- **可折叠卡片**：点击节点 / 订阅的标题栏即可展开或收起列表
- **节点列表**：协议彩色缩写标签（VL/VM/SS/HY2/TJ/TU/ATLS），启用节点带呼吸状态点和左侧霓虹竖条
- **图标按钮**：复制 / 二维码 / 编辑 / 删除 / 登出等用 Naive UI 圆形按钮 + 内联 SVG 图标，跨平台一致、跟随主题色
- **快捷操作**：响应式网格，手机每行 2 个、宽屏一排平铺
- **动效**：品牌标题流光、背景缓慢流动、卡片入场、登录页粒子背景、按钮点击波纹
- **移动端适配**：响应式布局，列表项内容自动截断、操作按钮不溢出；弹窗默认居中、不自动聚焦输入框，软键盘弹出时自适应上移避免遮挡

## 数据流

```
浏览器 → panel(FastAPI) → 写 SQLite
                        → 生成 data/config/config.json（服务端配置）
                        → 生成 data/sub/sub_N.json（客户端订阅）
                        → docker restart sing-box（重载配置）
```

客户端拉订阅：`http://<IP>:8080/sub/download/<slug或token>`

## 维护

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

## 注意事项

- **容器名是写死的**：后端代码通过 `docker restart sing-box`、`docker exec sing-box ...` 控制代理核心，sing-box 容器名**必须叫 `sing-box`**。改 compose 里的 `container_name` 会让重启、检查更新、一键配置失效。
- **构建上下文**：生产 `backend/Dockerfile` 是多阶段，`COPY backend/...` 和 `COPY frontend/...` 需要项目根做 context。compose 里已设 `context: .` + `dockerfile: backend/Dockerfile`，不要改成 `./backend`。
- **host 网络**：panel 和 sing-box 都用 `network_mode: host`，重启时代理会短暂中断几秒。
- **docker.sock 挂载**：面板通过挂载 `/var/run/docker.sock` 控制 sing-box 容器，等同于宿主机 root 权限，注意面板的访问安全（改默认密码、别暴露公网无认证）。
- **构建资源**：`docker compose up -d --build` 会在本机编译前端（`npm install` + `vite`），瞬时吃满 CPU 和内存。2 核 / 2G 的小机器务必先配 swap（建议 4G），否则构建期间内存耗尽会拖垮整机、连带 sing-box 和面板失联。内存紧张时也可在别处构建镜像、服务器只跑 `docker compose up -d`（不带 `--build`）。