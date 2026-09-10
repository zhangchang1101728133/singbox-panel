# ── 阶段 1：构建 Vue 前端 ────────────────────────────────
FROM node:22-slim AS frontend-build
WORKDIR /build
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ── 阶段 2：Python 后端 + 托管前端产物 ────────────────────
FROM python:3.14-slim
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app/ ./app/

# 前端构建产物拷到 STATIC_DIR，由 FastAPI 托管
COPY --from=frontend-build /build/dist /app/static
ENV STATIC_DIR=/app/static

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
