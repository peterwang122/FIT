# FIT - 股票量化平台（可扩展骨架）

本项目定位为**只读展示系统**：读取你已有 MySQL 行情库，展示 K 线与任务状态。

- 前端：Vue3 + TypeScript + Vite + Lightweight Charts
- 后端：FastAPI + Celery + Redis
- 监控：Flower（任务管理页面）

## 关键改进

1. 前端主页升级为“行情中心 / 任务监控（Flower）”双 Tab。
2. 后端支持**现有数据库字段映射配置**，不再强绑定固定 ORM 字段。
3. 新增接口：
   - `GET /api/v1/stocks/symbols` 自动列出可选股票代码
   - `GET /api/v1/stocks/meta` 返回当前字段映射
4. Flower 通过 `docker compose` 一键启动，前端 Tab 可直接跳转。

## 配置（重点）

复制环境变量模板：

```bash
cp backend/.env.example backend/.env
```

请根据你真实数据库字段名修改这些配置（否则可能查不到数据）：

- `STOCK_TABLE_NAME`
- `STOCK_CODE_COLUMN`
- `STOCK_DATE_COLUMN`
- `STOCK_OPEN_COLUMN`
- `STOCK_HIGH_COLUMN`
- `STOCK_LOW_COLUMN`
- `STOCK_CLOSE_COLUMN`
- 其他可选字段：`PRE_CLOSE/CHANGE/PCT_CHG/VOL/AMOUNT`

## 启动

### 1) 启动基础依赖（MySQL/Redis/Flower）

```bash
docker compose up -d
```

### 2) 启动后端 API

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 3) 启动 Celery Worker

```bash
cd backend
celery -A app.workers.celery_app worker --loglevel=info
```

### 4) 启动前端

```bash
cd frontend
npm install
npm run dev
```

## Flower

- 默认地址：`http://127.0.0.1:5555`
- 前端“任务监控（Flower）”Tab 提供跳转按钮。
