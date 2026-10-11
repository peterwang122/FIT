# 立伟抖音日更：本地 ASR 接入与数据恢复

> 2026-10-09 晚间更新：用户要求今天执行后，已于 18:58 重载常驻服务并启用任务 30；19:00 正式调度已实际执行首轮，返回无更新并继续检查。股票任务已按原进度自动续采。详见 [晚间加载与启用记录](DOUYIN_LOCAL_ASR_ACTIVATION_2026-10-09.md)。下文保留上午交付时的状态。

记录时间：2026-10-09，中国时间。此前单条作品探测见 [10 月 8 日实测记录](DOUYIN_TRANSCRIPTION_PROBE_2026-10-08.md)。

## 交付状态

正式代码已经将视频文案来源改为“已登录抖音页面的官方播放器 → 官方媒体下载 → 本机 turbo ASR → 原严格四项解析器”。持久解释器和模型缓存已建立。使用新代码的独立手工进程成功恢复 2026-10-08 数据，并通过数据库与 FIT 服务方法核验看板。

**常驻 `stock-temp` 服务尚未加载新代码。** 11:04 的检查确认任务 34“期权分钟行情采集”仍在 Celery 执行，运行记录为 6167，且工作进程与 `stock-temp` 保持连接。服务监听 PID 仍为 2514。空闲前置检查未通过，未执行重载，不能把本次手工成功写成常驻服务部署成功。

任务 30 仍为 `enabled=0`、`schedule_time=19:00`。本次直接调用采集器，没有新增任务中心运行记录，没有启用日更。未重启 FIT API、Celery、采集服务或 VPN，也未创建分支、提交、PR 或推送。

## 已恢复的数据

目标作品：[立伟 2026-10-08 作品](https://www.douyin.com/video/7694264298039014619)，页面发布时间 19:55，官方播放器时长约 137.486 秒。

| 指数 | 情绪值 | 规范记录 ID |
| --- | ---: | ---: |
| 上证50 | 23 | 1725 |
| 沪深300 | 13 | 1726 |
| 中证500 | 8 | 1727 |
| 中证1000 | 9 | 1728 |

- 原始表 `douyin_index_emotion_daily` 的记录 84 从失败恢复为 `SUCCESS`，保留目标作品、日期与指定作者身份；提取方法为 `local_turbo_asr+local_parser`，兼容现有 32 字符字段，无数据库结构修改。
- 规范表 `excel_index_emotion_daily` 恰有目标日四项记录，`source_file=douyin:7694264298039014619`，`data_source=douyin_local_asr`。
- 使用现有 `quant_index.sync_daily` 重算目标日，报告处理 11 条看板记录。四项情绪值如上，上证指数按现有逻辑派生为 **13.25**。
- FIT 原有四行落库校验通过。调用现有情绪与 CN 看板缓存清理方法后，再读取 `StockService` 和 `QuantService`，返回值一致。首次清理计数为 0/0；重复核验清理已生成的情绪缓存 1 项、CN 看板缓存 5 项。
- FIT 浏览器打开后停在登录页；本次看板核验依据实际数据库和服务层返回值，不声称完成登录后的页面核验。

手工采集从 10:47:12 至 10:51:02 返回 `SUCCESS`。再次执行返回 `ALREADY_PROCESSED`；原始记录、四条规范记录、看板记录及媒体与文案文件的修改时间均保持一致。当天 2026-10-09 检查返回 `NO_UPDATE`，最新合格作品仍为 10 月 8 日。

## 官方来源与转写证据

当前浏览器播放器使用 blob/MSE，实际取得同一页面主框架的两条官方 MP4 响应。下载后在隔离 PyAV 环境确认恰有一条纯视频和一条纯音频；核对时长与可见播放器视频分辨率后，使用对应音频转写。

| 媒体 | 核验结果 |
| --- | --- |
| 来源主机 | `v26-web.douyinvod.com`，完整下载均为 HTTP 200、`video/mp4` |
| 视频 | 14,133,396 字节；137.466667 秒；1270×720；无音轨 |
| 音频 | 831,784 字节；137.646485 秒；无视频流 |
| 合计 | 14,965,180 字节 |
| 视频 SHA-256 | `27aa502add580370263d3195f813a189b2312ffc0d18b9fb53b4deff9c835b6e` |
| 音频 SHA-256 | `e918eeafb0c58039b10a83fbc76f93c7c81cd4b41374e580f257ebeb7778e898` |

这是与原探测视频不同的官方媒体封装，不能宣称字节相同。作品 ID、作者、页面发布日期均一致；未经手工修改的转写原文与原探测完全相同：783 字符、18 个时间戳片段，原文 SHA-256 为 `67571ea69d12f3c1541b9ae5100b45a6dfc8cf40c93ae0ee47124c5bda4b043b`。从本次新下载的视频提取 106 秒、110 秒原始帧，逐项确认图表为 23、13、8、9。

私有运行证据位于忽略目录 `runtime/douyin_asr/`：

- `manual-recovery-attempt7.json`、`manual-recovery-repeat.json`：实际采集结果。
- `recovery-verified-first.json`、`recovery-verified-repeat.json`：SQL、FIT 校验、缓存及服务层返回值。
- `final-consistency.json`、`transcript-consistency.json`：幂等、配置及原文一致性。
- `current-date-no-update.json`、`deployment-state-final.json`：当天无更新与常驻服务忙碌证据。
- `artifacts/2026-10-08-7694264298039014619/`：媒体、来源元数据、转写 JSON/文本及 `chart-106s.png`、`chart-110s.png`。

新链路不持久化带签名播放地址。下载地址仅经子进程 stdin 传递，不进入参数、环境变量或日志；来源证据只保留公开作品身份、CDN 主机、字节哈希与媒体属性。ASR 根目录及作品目录权限为 0700，媒体、文案与核验证据为 0600。

## 持久运行环境

根目录：`/Users/wanghequan/PycharmProjects/FIT/runtime/douyin_asr/`。运行时不依赖 `/private/tmp`。

| 项目 | 配置 |
| --- | --- |
| 独立解释器 | `venv/bin/python`，Python 3.10.20 |
| 模型缓存 | `model-cache/`，已物化在持久目录 |
| 引擎 | faster-whisper 1.2.1 |
| 模型 | `mobiuslabsgmbh/faster-whisper-large-v3-turbo` |
| 模型 revision | `0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf` |
| 计算限制 | CPU int8，2 线程、1 worker，nice +10 |
| 离线使用 | `local_files_only=True`、`HF_HUB_OFFLINE=1` |
| 依赖记录 | `requirements.lock`，SHA-256 `153ec0116b44aca7c3bcc99ab46efa5713f9800e2013f62fc42e017f7dd1d43d` |

未向原 FIT 或采集生产环境追加 ASR 依赖。已在持久环境重新转写确认与探测原文一致，并在实际采集时观察到 ASR 子进程低优先级、约两核的 CPU 使用。

## 实现与兼容约束

采集仓库 `/Users/wanghequan/PycharmProjects/akshareProkect` 的修改：

- `collectors/douyin_emotion.py`：视频正式路径调用本地 ASR，登录只要求抖音；保留指定主页、日期与 15:00 门槛、作品去重、非情绪排除、图文 OCR、`NO_UPDATE` 和单实例锁。置顶作品不参与选择。
- `collectors/douyin_local_asr.py`：验证作品 ID、作者主页与名称、页面发布时间和可见播放器；只允许官方 HTTPS 媒体，重定向同样校验；完整下载、长度与媒体流角色核验后转写。
- `collectors/douyin_media_worker.py`、`douyin_media_inspector.py`、`douyin_asr_worker.py`：分别隔离下载、媒体核验和离线转写。下载硬超时 90 秒，媒体核验 60 秒，ASR 480 秒；超时或取消后杀死并回收子进程，清理下载残片。下载连接失败最多两次，每次重新取得播放器地址。
- `db/db_tool.py`：区分本地 ASR 数据来源；保持 Excel 和手工任务中心数据的保护规则。
- `services/stock_temp_service.py`：保留 `/collect-douyin-coze-emotion-daily` 路由和 `douyin_coze_emotion_daily` 任务键；正式浏览器不打开 Coze。健康接口新增运行环境就绪状态与活动请求计数，服务总超时会请求取消浏览器及转写任务。

已有严格四项解析逻辑未放宽。名称、数字缺失或歧义仍拒绝写入，四项不以默认值 50、旧值或猜测补齐。成功缓存需匹配作者、作品和日期；失败的旧 Coze 文案不作为本地 ASR 缓存恢复。旧 Coze 辅助函数保留供兼容，但正式路径没有自动回退。

FIT 生产代码未修改；只扩展了 `backend/tests/test_task_service_collection_validation.py`，覆盖本地 ASR 成功、恢复、幂等返回、超时续查、规范表缺一项时失败及暂停开关保持原样。

## 配置保护与验证

前后配置指纹完全一致：43 条 `quant_strategy_configs`、53 条任务的静态配置、5 位用户的通知/邮箱配置、16 个风险/市场状态/通知设置以及 9 个相关源文件。没有修改风险规则、策略参数、邮件或微信通知配置。相关私有证据只保存字段哈希，不保存配置值。

最终检查：

```text
采集仓库：108 passed
  test_douyin_coze_emotion.py
  test_douyin_local_asr.py
  test_douyin_local_asr_service.py
  test_hk_index_futures_daily_service.py

FIT：93 passed
  test_task_service_collection_validation.py
  test_task_service_market_scope.py
  test_collector_daily_retry.py

本次相关 Python 文件 compileall：通过
两个仓库 git diff --check：通过
```

覆盖下载失败及边界、来源错配、缺音轨、分离音视频角色歧义、媒体时长/分辨率不匹配、转写超时与取消、严格解析、幂等、登录失效、置顶排除、图文 OCR 和原服务兼容。

两仓库均留在 `main`，基准 HEAD 分别为：FIT `8012c9b427923eaf14de94cf776d8513c7dc983b`；采集仓库 `c56bca69987a988e7c78c132903796a5da7b0d04`。FIT 中与本次无关的已有工作区修改均保留。

## 尚需完成的常驻服务加载

只需在采集空闲后重载 `com.akshareProkect.stock-temp`，无需重启 FIT API 或 Celery。私有辅助脚本 `runtime/douyin_asr/deploy_stock_temp.py` 在重载前检查两名 Celery worker 的 active/reserved/scheduled、任务中心未结束记录、服务连接、抖音锁和健康状态；任务 30 必须保持暂停且时间为 19:00。历史运行记录 4898 已单独核查为没有对应 Celery 活动的旧记录，本次未改写其状态。

加载后应确认新 PID 的 `/health` 返回 `douyin.extraction_engine=local_turbo_asr`、`asr_ready=true` 以及活动请求计数，再通过保留的正式 HTTP 路由核验既有目标日的幂等结果及当天 `NO_UPDATE`。这部分尚未执行，因此当前交付不包含常驻 HTTP 服务新链路的实跑证明。

抖音登录仍可能失效，页面结构和官方媒体传输形态也可能变化；遇到身份、来源或解析无法确认时明确失败。本次一条真实作品的验证不构成长期日更稳定性保证。
