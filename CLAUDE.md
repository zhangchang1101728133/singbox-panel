# singbox-panel

sing-box 代理节点管理面板。支持节点管理（VMESS/VLESS/Trojan/SS 等）、订阅管理、一键生成 sing-box 配置、QR 码分享。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.14 + FastAPI + SQLite（aiosqlite） |
| 前端 | Vue 3.5 + Vite 5 + **TypeScript** |
| UI | Naive UI 2.44+ |
| 状态 | Pinia |
| 路由 | Vue Router 4 |
| 其他 | qrcode.vue（二维码）|
| 部署 | Docker multi-stage（单容器，FastAPI 托管 Vue 静态产物）+ sing-box 容器 |

## 项目结构

```
singbox-panel/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 主入口，挂载路由，托管静态文件
│   │   ├── models/
│   │   │   └── database.py      # SQLite 初始化（aiosqlite），节点/订阅表
│   │   ├── routers/
│   │   │   ├── auth.py          # 登录/登出/me（httpOnly cookie）
│   │   │   ├── nodes.py         # CRUD 节点
│   │   │   ├── subscription.py  # 订阅管理 + 生成链接
│   │   │   └── api.py           # 版本检查/升级、一键配置、协议清单
│   │   └── services/
│   │       ├── protocols.py     # 协议注册表（唯一数据源）
│   │       ├── singbox.py       # 生成 config.json + 校验 + 容器控制
│   │       └── updater.py       # sing-box 升级（compose + 备份 + 回滚）
│   ├── Dockerfile               # multi-stage：node 构建 → python 托管
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── types/index.ts            # 全局类型：AuthUser, Node, Subscription
│   │   ├── api/client.ts             # fetch 封装（JSON + form）, 401 跳登录
│   │   ├── stores/
│   │   │   ├── auth.ts               # Pinia：user, checked, fetchMe, login, logout
│   │   │   └── theme.ts              # Pinia：mode('dark'|'light'), toggle
│   │   ├── router/index.ts           # Vue Router，beforeEach 守卫
│   │   ├── components/
│   │   │   ├── AppIcon.vue           # 内联 SVG 图标（无外部图标库）
│   │   │   ├── NodeList.vue          # 节点列表
│   │   │   ├── NodeFormModal.vue     # 添加/编辑节点弹窗
│   │   │   ├── SubscriptionList.vue  # 订阅列表
│   │   │   ├── SubFormModal.vue      # 添加/编辑订阅弹窗
│   │   │   ├── QuickActions.vue      # 快捷操作区
│   │   │   └── StatsBar.vue          # 状态栏
│   │   ├── views/
│   │   │   ├── Login.vue             # 登录页，Canvas 粒子背景动画
│   │   │   └── Dashboard.vue         # 主面板
│   │   ├── App.vue                   # NConfigProvider + NMessageProvider
│   │   └── main.ts                   # 挂载 + 全局 ripple + 软键盘检测
│   ├── tsconfig.json
│   ├── vite.config.js
│   └── package.json
├── docker-compose.yml               # 生产：sing-box + panel 两容器
├── docker-compose.dev.yml           # 开发：仅 panel，前端 vite dev server
└── data/                            # 持久化数据目录（挂载到容器）
    ├── config/                      # sing-box 生成的 config.json
    └── sub/                         # 订阅文件
```

## 关键设计

### 鉴权（routers/auth.py）
PyJWT 签发与验证 token，存储在 httpOnly cookie。  
环境变量：`ADMIN_USER`、`ADMIN_PASS`、`SECRET_KEY`。

### 数据库（models/database.py）
SQLite + aiosqlite，异步操作。节点和订阅各有独立表。  
启动时自动 `init_db()`，无需手动迁移。

### 协议注册表（services/protocols.py）
协议（inbound/outbound 生成、表单字段、默认端口、最低 sing-box 版本）的唯一数据源。  
新增协议只改这一个文件：配置生成、一键配置、前端表单（`GET /api/protocols`）都从这里读取。  
`min_version` 用于按运行中的 sing-box 版本判断可用性，不支持的协议自动隐藏。

### sing-box 配置生成（services/singbox.py）
根据数据库中的节点生成标准 sing-box `config.json`，写入 `/data/config/`。  
sing-box 容器以只读方式挂载该目录。

写入前会先用 `sing-box check` 校验（`validate_generated`）：不通过就直接 400，不写库也不重启，
避免一次误操作让正在跑的代理起不来。

### sing-box 升级（services/updater.py）
- 检查版本：**不做 `docker pull`**，只查 GitHub Releases API + 本地 `sing-box version`。
- 升级：`docker compose pull` + `up -d`，完全沿用 compose 声明的网络/挂载/restart 策略。
  （旧实现用 `docker rm -f` + `docker run` 硬编码参数重建，会让容器脱离 compose 管理。）
- 顺序：备份 config.json → 拉镜像 → 重建 → `sing-box check` → 失败自动回滚并重建回旧版本。
- 需要面板容器挂载 compose 插件与项目目录（见 docker-compose.yml 的 `COMPOSE_DIR`）。

### 软键盘适配（main.ts）
通过 `window.visualViewport` 检测软键盘弹出，给 `body` 加 `kb-open` 类，弹窗自适应上移，适配移动端。

### 主题系统（stores/theme.ts）
`mode` 值为 `'dark' | 'light'`（字符串），与 `data-theme` attribute 对应。  
默认暗色，`localStorage` 持久化，key 为 `panel-theme`。

### API 客户端（api/client.ts）
统一 fetch 封装，支持 JSON body 和 form-urlencoded。  
401 时自动跳转到登录页（通过 vue-router）。

## 本地开发

```bash
# 后端（需要 Python 3.14+）
cd backend
pip install -r requirements.txt
ADMIN_USER=admin ADMIN_PASS=admin123 SECRET_KEY=dev \
  uvicorn app.main:app --reload --port 8080

# 前端（另开终端）
cd frontend
npm install
npm run dev   # Vite dev server，代理到 localhost:8080
```

前端访问 http://localhost:5173，后端 http://localhost:8080

## Docker 部署（生产）

```bash
# 启动 sing-box + panel
docker compose up -d --build

# 访问面板
open http://<服务器IP>:8080
```

自定义账号密码（推荐通过 `.env` 文件）：

```bash
# 创建 .env 文件
cat > .env <<EOF
SECRET_KEY=your-strong-secret-key
ADMIN_USER=youruser
ADMIN_PASS=yourpass
EOF

docker compose up -d --build
```

## Docker 开发模式

```bash
# 仅启动后端，前端用 vite dev server
docker compose -f docker-compose.dev.yml up -d

cd frontend
npm install
npm run dev
```

## API 端点

```
POST /auth/login              { username, password } → 设置 session cookie
POST /auth/logout             → 清除 cookie
GET  /auth/me                 → 返回当前用户信息

GET  /nodes                   → 列出所有节点
POST /nodes                   → 创建节点
PUT  /nodes/{id}              → 更新节点
DELETE /nodes/{id}            → 删除节点

GET  /sub                     → 列出所有订阅
POST /sub                     → 创建订阅
PUT  /sub/{id}                → 更新订阅
DELETE /sub/{id}              → 删除订阅
GET  /sub/{id}/link           → 获取订阅链接

GET  /api/protocols           → 协议清单（按 sing-box 版本标记 available）
GET  /api/singbox/version     → 当前/最新版本，是否有更新（不拉镜像）
POST /api/singbox/update      → 升级 sing-box（备份 + compose 重建 + 校验 + 回滚）
POST /api/quick-setup         → 一键配置所选协议
GET  /health                  → 健康检查
```

## TypeScript 类型（src/types/index.ts）

```typescript
AuthUser      // username
Node          // id, name, server, port, type, ...（sing-box 节点字段）
Subscription  // id, name, url, nodes?, updated_at?
```
