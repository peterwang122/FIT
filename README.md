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
   - `GET /api/v1/stocks/symbols` 返回股票代码+名称（来自 `stock_basic_info`），并支持关键字查询
   - `GET /api/v1/stocks/meta` 返回当前字段映射
6. 打开页面时会把 `stock_basic_info` 全量加载到 Redis 缓存，前端输入框实时下拉搜索（代码/名称均可）。
7. K 线查询已取消默认条数限制（返回该代码全部区间数据，可用 start_date/end_date 过滤）。

## 关于 SQL 初始化文件

本项目是只读展示系统，不负责创建你的业务行情表。
因此原先示例 `backend/sql/init.sql` 已移除（非必须）。

## 配置（重点）

复制环境变量模板：

```bash
cp backend/.env.example backend/.env
```

当前已内置你提供的字段映射（`stock_code/date/open_price/high_price/low_price/close_price/price_change_rate/volume/turnover`），通常**不需要**在 `.env` 再配置映射字段。

只有当数据库结构变化时，才需要在 `.env` 中覆盖 `STOCK_*` 配置。

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

如果 MySQL 账号认证方式是 `caching_sha2_password` 或 `sha256_password`，后端还需要依赖 `cryptography`。
当前它已经加入 [backend/requirements.txt](C:/Users/Administrator/PycharmProjects/FIT/backend/requirements.txt)，重新执行一次安装依赖即可。

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


若你的库很大、索引不完善导致响应慢，可在前端设置：

- `VITE_API_TIMEOUT_MS=60000`（或更大）

另外后端 K 线默认 `limit` 已下调为 240，减少首屏查询开销。

## Flower

- 默认地址：`http://127.0.0.1:5555`
- 前端“任务监控（Flower）”Tab 点击会直接打开该地址。


## 前端 Network Error 说明

若出现 `AxiosError: Network Error`，通常是跨域或前端直接请求错误地址导致。

当前默认已处理：

- 前端默认请求同源 `/api/v1`
- Vite 开发服务器代理 `/api -> http://127.0.0.1:8000`
- 后端已开启 CORS（`CORS_ALLOW_ORIGINS`）

如需手动指定后端地址，可设置：

- `VITE_API_BASE_URL=http://你的地址:8000/api/v1`
