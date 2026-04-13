# FIT 股票量化系统

FIT 是一个基于 `Vue 3 + FastAPI + Celery + Redis + MySQL` 的股票量化分析平台。

当前项目已经包含这些主要能力：

- 首页行情与总览
- 个股行情
- 量化分析
  - 指数
  - 股票
  - 条件策略
  - 策略回测
- 用户体系
  - 手机验证码登录
  - 账号密码登录
  - 游客账号
- 用户隔离的策略空间
- 任务中心
  - 任务管理
  - Flower 任务监控
  - root 专属“全部策略”
- 站内消息提醒

## 1. 技术栈

- 前端：Vue 3、TypeScript、Vite、Pinia、Vue Router、Lightweight Charts
- 后端：FastAPI、SQLAlchemy、Pydantic Settings
- 异步任务：Celery、Redis、Flower
- 数据库：MySQL

## 2. 目录说明

- [frontend](C:\Users\Administrator\PycharmProjects\FIT\frontend)：前端工程
- [backend](C:\Users\Administrator\PycharmProjects\FIT\backend)：后端工程
- [docs](C:\Users\Administrator\PycharmProjects\FIT\docs)：补充文档

## 3. 运行前准备

你至少需要准备：

- MySQL
- Redis
- Python 环境
- Node.js

如果你要用到这些功能，还需要额外准备：

- 手机验证码登录：阿里云短信认证服务配置
- 定时通知任务：SMTP 邮件配置
- 股票后复权临时采集：采集端服务

## 4. 环境变量

先复制环境变量模板：

```powershell
Copy-Item backend\.env.example backend\.env
```

然后按你自己的环境修改 [backend/.env](C:\Users\Administrator\PycharmProjects\FIT\backend\.env)。

最关键的配置通常是：

- `DATABASE_URL`
- `REDIS_URL`
- `ROOT_USERNAME`
- `ROOT_PASSWORD`
- `GUEST_USERNAME`
- `GUEST_PASSWORD`
- `COLLECTOR_BASE_URL`
- `FLOWER_URL`
- 短信配置
- SMTP 配置

说明：

- `docker-compose.yml` 只会帮你启动 `Redis + Flower`
- **不会**帮你启动 FastAPI、Celery worker、Celery beat、前端 dev server

## 5. 启动顺序

### 5.1 启动 Redis 和 Flower

```powershell
docker compose up -d
```

默认端口：

- Redis：`6379`
- Flower：`5555`

### 5.2 启动后端 API

```powershell
cd backend
C:\Users\Administrator\miniconda3\envs\FIT\python.exe -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

默认地址：

- API：[http://127.0.0.1:8000](http://127.0.0.1:8000)

### 5.3 启动 Celery Worker

```powershell
cd backend
celery -A app.workers.celery_app worker --loglevel=info -P solo
```

### 5.4 启动 Celery Beat

```powershell
cd backend
celery -A app.workers.celery_app beat --loglevel=info
```

这一步很重要：

- **现在 Celery 不是只启动一个服务就够了**
- 如果你只启动 `worker`，手动触发任务通常能跑，但**定时任务不会按时间自动触发**
- 要让任务中心里的“定时采集 / 定时通知”正常工作，必须同时启动：
  - `worker`
  - `beat`

### 5.5 启动前端

```powershell
cd frontend
npm install
npm run dev
```

默认地址：

- 前端：[http://127.0.0.1:5173](http://127.0.0.1:5173)

## 6. 本地开发时最常见的 4 个进程

如果你是完整开发任务中心、回测、通知这套链路，通常要同时跑这 4 组：

1. `uvicorn`
2. `celery worker`
3. `celery beat`
4. `vite`

再加上：

- `docker compose up -d` 提供的 `Redis + Flower`

## 7. 登录说明

系统支持三种进入方式：

- 手机验证码登录/注册
- 账号密码登录
- 游客一键进入

内置账号来自 [backend/.env](C:\Users\Administrator\PycharmProjects\FIT\backend\.env)：

- `root`
- `guest`

建议你在正式使用前修改默认密码。

## 8. 任务中心说明

任务中心目前包含：

- `任务管理`
- `任务监控`
- `全部策略`（root 专属）

任务类型目前有：

- 采集任务：仅 root 可创建
- 通知任务：root 和普通用户可创建，guest 不可创建

注意：

- 采集任务和通知任务的“按日定时触发”，依赖 `celery beat`
- Flower 只是监控页，不负责定时调度

## 9. 数据口径说明

### 个股行情

- 使用个股行情同口径的日线数据
- 不走股票量化的后复权链路

### 股票量化 / 股票策略回测

- 当前使用后复权链路
- 对接采集端时请参考 [docs/STOCK_HFQ_COLLECTION_MIGRATION.md](C:\Users\Administrator\PycharmProjects\FIT\docs\STOCK_HFQ_COLLECTION_MIGRATION.md)

### 条件策略

- 单标的模式：支持指数 / 个股 / ETF
- 全市场扫描：当前支持 `stock / etf`
- `stock` 扫描使用个股行情同口径的非复权日线

## 10. 全市场扫描说明

全市场扫描现在已经做了超时治理，规则如下：

- 必须手选 `scan_start_date / scan_end_date`
- 扫描结果会生成 `scan_result_id`
- 条件策略页翻页不会重新扫全市场
- 策略回测页会复用同一个扫描快照做事件勾选回测
- 只有扫描相关请求单独放宽超时到 `300000ms`

## 11. 常见问题

### 11.1 任务中心里定时任务不执行

通常是因为你只启动了 `worker`，没有启动 `beat`。

请确认下面两个进程都在跑：

```powershell
celery -A app.workers.celery_app worker --loglevel=info -P solo
celery -A app.workers.celery_app beat --loglevel=info
```

### 11.2 Flower 打得开，但任务还是不自动跑

Flower 只是监控，不是调度器。

你还需要：

- `worker`
- `beat`

### 11.3 手机验证码发不出去

请检查：

- `ALIBABA_CLOUD_ACCESS_KEY_ID`
- `ALIBABA_CLOUD_ACCESS_KEY_SECRET`
- `ALIYUN_SMS_SIGN_NAME`
- `ALIYUN_SMS_TEMPLATE_CODE`

本地开发如果短信配置不完整，后端会回退到调试模式，把验证码打到后端日志里。

### 11.4 通知任务不发邮件

请检查 SMTP 配置：

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_USE_TLS`
- `SMTP_FROM_EMAIL`
- `SMTP_FROM_NAME`

### 11.5 股票后复权采集失败

请确认：

- 采集端已经按 [docs/STOCK_HFQ_COLLECTION_MIGRATION.md](C:\Users\Administrator\PycharmProjects\FIT\docs\STOCK_HFQ_COLLECTION_MIGRATION.md) 切到 `hfq`
- `COLLECTOR_BASE_URL` 正确
- Celery worker 正常运行

## 12. 推荐启动命令汇总

### 基础依赖

```powershell
docker compose up -d
```

### 后端

```powershell
cd backend
uvicorn app.main:app --reload --port 8000
```

### Celery Worker

```powershell
cd backend
celery -A app.workers.celery_app worker --loglevel=info -P solo
```

### Celery Beat

```powershell
cd backend
celery -A app.workers.celery_app beat --loglevel=info
```

### 前端

```powershell
cd frontend
npm run dev
```

## 13. 构建检查

前端：

```powershell
cd frontend
npm run build
```

后端语法检查：

```powershell
C:\Users\Administrator\miniconda3\envs\FIT\python.exe -m compileall backend/app
```
