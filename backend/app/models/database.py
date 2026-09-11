"""数据库模型和连接管理"""
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

DB_PATH = Path(os.getenv("DATA_DIR", "/data")) / "db" / "singbox.db"


@asynccontextmanager
async def get_db():
    """异步数据库上下文管理器"""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


async def init_db():
    """初始化数据库表"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                server TEXT NOT NULL,
                server_port INTEGER NOT NULL,
                enabled BOOLEAN DEFAULT TRUE,
                config JSON NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT NOT NULL,
                token TEXT UNIQUE NOT NULL,
                slug TEXT DEFAULT '',
                node_ids JSON,
                enabled BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # 如果表已存在但没有 slug 字段，添加它
        try:
            await db.execute("SELECT slug FROM subscriptions LIMIT 1")
        except:
            await db.execute("ALTER TABLE subscriptions ADD COLUMN slug TEXT DEFAULT ''")

        await db.commit()

        # 迁移：早期版本的订阅 token 是 f"sub_{id}"，可枚举。下载接口未认证，
        # token 即唯一凭据，所以必须换成随机值。
        # 幂等：只替换恰好是 "sub_"+纯数字 的旧格式，随机 token 不会被误伤。
        cursor = await db.execute("SELECT id, token FROM subscriptions")
        legacy = [
            sub_id for sub_id, token in await cursor.fetchall()
            if token.startswith("sub_") and token[4:].isdigit()
        ]
        for sub_id in legacy:
            await db.execute(
                "UPDATE subscriptions SET token = ? WHERE id = ?",
                (secrets.token_urlsafe(24), sub_id),
            )
        if legacy:
            await db.commit()

        # 插入默认管理员
        cursor = await db.execute("SELECT COUNT(*) FROM users WHERE is_admin = TRUE")
        count = (await cursor.fetchone())[0]
        if count == 0:
            import bcrypt
            admin_user = os.getenv("ADMIN_USER", "admin")
            admin_pass = os.getenv("ADMIN_PASS", "admin123")
            password_hash = bcrypt.hashpw(admin_pass.encode(), bcrypt.gensalt()).decode()
            await db.execute(
                "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, TRUE)",
                (admin_user, password_hash)
            )
            await db.commit()
