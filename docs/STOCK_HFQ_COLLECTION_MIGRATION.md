# 股票后复权采集改造说明

本文档给采集端使用，说明 FIT 已经把股票量化主链路从前复权切到后复权，采集端需要如何配合改造。

## 背景

FIT 当前的股票量化页面、股票策略筛选、股票回测、任务中心采集任务、通知任务里的股票策略摘要，都会直接使用整段股票复权日线来计算指标和回测结果。

如果继续使用前复权数据：

- 历史价格会被未来的分红送转复权因子回写
- 回测和指标计算会带入未来信息
- 这会让股票量化结果存在未来函数风险

因此，FIT 不再接受前复权作为股票量化正式口径，后续统一切到后复权。

## 采集端改造目标

采集端需要把当前“股票前复权临时采集服务”改为“股票后复权临时采集服务”。

### 数据口径

- 采集接口：`ak.stock_zh_a_daily(adjust="hfq")`
- 目标表：`stock_hfq_daily_data`
- FIT 不再读取 `stock_qfq_daily_data`

### 表结构

`stock_hfq_daily_data` 建议沿用当前 `stock_qfq_daily_data` 的字段结构，避免 FIT 再做额外适配。建议至少包含：

- `stock_code`
- `prefixed_code`
- `stock_name`
- `trade_date`
- `open_price`
- `close_price`
- `high_price`
- `low_price`
- `price_change_amount`
- `price_change_rate`
- `volume`
- `turnover_amount`
- `outstanding_share`
- `turnover_rate`
- `data_source`
- `request_start_date`
- `request_end_date`
- `refresh_batch_id`

字段语义不变，只是整张表改为后复权数据。

## 服务接口要求

采集端可以继续保留当前的通用 HTTP 路径：

- `GET /health`
- `POST /collect`

FIT 侧不会要求采集端把 `/collect` 改名，只要求：

- `POST /collect` 现在采集的是后复权
- 返回结构与当前保持兼容
- 文档、说明、日志不要再写“前复权”

### 请求示例

```json
{
  "stock_code": "600000",
  "start_date": "2020-01-01",
  "end_date": "2026-04-11"
}
```

### 成功响应要求

以下状态仍视为成功：

- `SUCCESS`
- `UNCHANGED`

返回字段保持兼容即可，例如：

```json
{
  "status": "SUCCESS",
  "stock_code": "600000",
  "prefixed_code": "sh600000",
  "effective_start_date": "2020-01-01",
  "effective_end_date": "2026-04-11",
  "refreshed": true,
  "unchanged": false,
  "deleted_rows": 1200,
  "written_rows": 1450
}
```

## 数据刷新规则

建议继续沿用当前临时采集服务的刷新规则：

- 按 `stock_code` 查询 `stock_info_all` 的上市日期
- 若查不到上市日期，则回退到 `1991-01-01`
- `effective_start_date = max(request.start_date, 上市日期/1991-01-01)`
- `effective_end_date = request.end_date 或 今日`
- 若请求区间与该股票最近一次请求区间完全一致，则返回 `UNCHANGED`
- 若请求区间变化，则删除该股票在目标表中的全部旧数据后整批重写

只是将目标从前复权改为后复权。

## FIT 侧已经切换的接口

FIT 前端和后端已经统一切到 `hfq` 命名，采集端无需实现这些路径，但要知道 FIT 现在内部语义已经变更：

- `GET /api/v1/stocks/{ts_code}/hfq-kline`
- `POST /api/v1/stocks/hfq-collect`
- `GET /api/v1/stocks/hfq-collect/{task_id}`
- Celery 任务名：`tasks.collect_stock_hfq_data`

其中：

- FIT 对前端暴露的是 `hfq-*` 路径
- FIT 对采集端仍然调用 `POST /collect`

## 首次切换建议

因为这次是直接从前复权切到后复权，不保留 FIT 侧 qfq 兼容层，建议采集端上线前至少完成以下准备：

1. 建好 `stock_hfq_daily_data`
2. 改造 `/collect` 使其落后复权数据
3. 对当前 FIT 中会被实际使用的股票做一次初始化

至少优先覆盖：

- 已保存股票策略涉及的股票
- 已启用采集任务涉及的股票
- 已启用通知任务中关联股票策略涉及的股票

如果 `stock_hfq_daily_data` 尚未有数据，FIT 股票量化页和股票回测会因为没有后复权行情而无法正常计算。

## 采集端改造最小清单

采集端至少需要完成这些点：

1. 把 `adjust="qfq"` 改成 `adjust="hfq"`
2. 把写库目标从 `stock_qfq_daily_data` 改成 `stock_hfq_daily_data`
3. 服务说明和日志从“前复权”改成“后复权”
4. 保持 `POST /collect` 的请求和响应兼容
5. 准备一轮后复权初始化数据

## 注意事项

- 现有 `stock_qfq_daily_data` 可以保留作历史参考，但 FIT 不再读取它
- 个股行情页继续使用非复权日线，不在本次改造范围内
- 如果采集端暂时还没切完，FIT 股票量化功能不要继续用旧前复权表顶替后复权
