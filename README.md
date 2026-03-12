# FIT - 股票量化平台（可扩展骨架）

本仓库提供一个前后端分离的初始骨架，满足以下目标：

- 前端：Vue3 + TypeScript + Vite，面向 K 线展示与后续策略/回测模块扩展。
- 后端：FastAPI + Celery + MySQL，支持通过任务调用外部数据采集服务。
- 当前数据表：`stock_data`（日级别后复权数据）已作为核心数据模型接入。
- 预留模块：量化策略、回测系统、用户管理、相关性分析与深度学习分析。

## 目录结构

```text
backend/
  app/
    api/           # 路由层
    core/          # 配置
    db/            # 数据库连接
    models/        # ORM 模型
    schemas/       # Pydantic 模型
    services/      # 业务逻辑
    tasks/         # Celery 任务定义
    workers/       # Celery 启动入口
frontend/
  src/
    api/           # HTTP 请求封装
    views/         # 页面
    components/    # 组件
```

## 快速开始

### 后端

1. 复制环境变量模板：

```bash
cp backend/.env.example backend/.env
```

2. 启动依赖（MySQL/Redis，可按需修改）：

```bash
docker compose up -d
```

3. 安装依赖并运行：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

4. 启动 Celery Worker：

```bash
cd backend
celery -A app.workers.celery_app worker --loglevel=info
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

## 开发规划建议

- V1：股票搜索、日 K、基础指标（MA）、任务触发采集、任务状态查询。
- V2：策略管理、回测执行队列、结果可视化。
- V3：用户体系（鉴权、订阅、自选股）、分析任务（相关性、因子、深度学习实验）。
