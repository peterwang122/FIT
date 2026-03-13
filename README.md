# FIT - 股票量化平台（可扩展骨架）

本项目定位为**只读展示系统**：读取你已有 MySQL 行情库，展示 K 线与任务状态。

- 前端：Vue3 + TypeScript + Vite + Lightweight Charts
- 后端：FastAPI + Celery + Redis
- 监控：Flower（任务管理页面）

## 关键改进

1. 前端主页升级为“行情中心 / 任务监控（Flower）”双 Tab。
2. “任务监控”Tab 点击会直接打开 Flower 页面。
3. 后端支持**现有数据库字段映射配置**，不再强绑定固定 ORM 字段。
4. 新增数据库连接检查接口：`GET /api/v1/stocks/db-status`，可确认是否连上你的现有库。
5. 新增接口：
   - `GET /api/v1/stocks/symbols` 支持按关键字搜索股票代码
   - `GET /api/v1/stocks/meta` 返回当前字段映射
6. 前端首页默认展示代码 `002594`，其他代码可搜索后展示。

## 关于 SQL 初始化文件

本项目是只读展示系统，不负责创建你的业务行情表。
因此原先示例 `backend/sql/init.sql` 已移除（非必须）。

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

### 1) 启动基础依赖（Redis/Flower）

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

## 连接确认（你关心）

启动后访问：

- `GET http://127.0.0.1:8000/api/v1/stocks/db-status`

当返回 `connected=true` 且 `symbol_count > 0`，说明本项目已经连接上你现有数据库并可读取股票数据。
前端“行情中心”左侧也会显示同样的连接状态与样例代码。

## Flower

- 默认地址：`http://127.0.0.1:5555`
- 前端“任务监控（Flower）”Tab 点击会直接打开该地址。
