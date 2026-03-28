# 量化展示指数页性能优化方案

## 1. 目标

本文档只描述两件事：

1. 数据采集项目 `akshareProkect` 需要如何新增预计算结果表、如何回补和日更。
2. FIT 项目后续如何直接读取这张预计算表，对接成更快的“量化展示 > 指数”页面。

本次不要求在 FIT 中直接实现新增表、回补脚本或定时任务；这些工作都由数据采集项目完成。

## 2. 当前慢的根因

当前 FIT 里的“量化展示 > 指数”首屏慢，主要由以下三点叠加造成：

1. 页面初始化时会并发请求 4 组原始数据：
   - 指数 K 线
   - 情绪指标
   - 期现差
   - 涨跌家数
2. `fetchIndexKline()` 当前默认会拉整段历史，前端再本地计算 `MA / BOLL / MACD / KDJ / WR`。
3. 涨跌家数如果运行时现算，需要对 `stock_daily_data` 做很重的历史统计，外网访问时尤为明显。

结论：问题不只是“图多”，而是“多接口 + 全量历史 + 运行时统计”一起把首屏拖慢了。

## 3. 优化总思路

本方案采用以下固定策略：

- 数据侧：`全量预计算`
- 更新时机：`收盘后更新`
- FIT 对接方式：`直接读取共享 MySQL`
- 前端加载方式：`先 recent，再后台补 full`

也就是说：

1. 情绪指标、期现差、涨跌家数都提前算好，落到一张新表里。
2. FIT 指数页后续不再首屏分别现算这 3 组数据。
3. 指数 K 线本身仍然保持从现有指数日线表读取，技术指标仍由前端按用户参数本地计算。

## 4. 数据项目侧新增表

### 4.1 表名

固定新增表：

`quant_index_dashboard_daily`

### 4.2 建议字段

```sql
CREATE TABLE `quant_index_dashboard_daily` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `trade_date` DATE NOT NULL,
  `index_code` VARCHAR(32) NOT NULL,
  `index_name` VARCHAR(64) NOT NULL,
  `emotion_value` DECIMAL(18,6) NOT NULL DEFAULT 50,
  `main_basis` DECIMAL(18,6) NOT NULL DEFAULT 0,
  `month_basis` DECIMAL(18,6) NOT NULL DEFAULT 0,
  `breadth_up_count` INT NOT NULL DEFAULT 0,
  `breadth_total_count` INT NOT NULL DEFAULT 0,
  `breadth_up_pct` DECIMAL(18,6) NOT NULL DEFAULT 0,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_quant_index_dashboard_daily_code_date` (`index_code`, `trade_date`),
  KEY `idx_quant_index_dashboard_daily_trade_date` (`trade_date`),
  KEY `idx_quant_index_dashboard_daily_name_date` (`index_name`, `trade_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 4.3 指数字段要求

该表必须直接落 5 个展示指数，不要只落 4 个核心指数：

- 上证指数
- 上证50
- 沪深300
- 中证500
- 中证1000

`index_code` 必须与 FIT 当前 `/stocks/indexes/options` 返回的 `code` 完全一致，避免后续 FIT 再做二次映射。

## 5. 各字段计算口径

### 5.1 emotion_value

#### 四大指数

以下 4 个指数直接使用 `excel_index_emotion_daily`：

- 上证50
- 沪深300
- 中证500
- 中证1000

#### 上证指数

上证指数不单独取源表，而是按四大指数同日平均计算：

```text
上证指数 emotion_value
= (上证50 + 沪深300 + 中证500 + 中证1000) / 4
```

规则：

- 某个交易日如果 4 个值都存在，直接平均
- 某个交易日如果只有部分存在，建议只对存在值求平均
- 某个交易日如果 4 个都不存在，则写 `50`

### 5.2 main_basis / month_basis

#### 四大指数

四大指数直接取现有期现差结果：

- 上证50：`IHM / IHM0`
- 沪深300：`IFM / IFM0`
- 中证500：`ICM / ICM0`
- 中证1000：`IMM / IMM0`

口径不变：

```text
main_basis = 主连期货收盘价 - 现货指数收盘价
month_basis = 当月连续期货收盘价 - 现货指数收盘价
```

#### 上证指数

上证指数按四大指数同日平均计算：

```text
上证指数 main_basis
= (上证50 main_basis + 沪深300 main_basis + 中证500 main_basis + 中证1000 main_basis) / 4

上证指数 month_basis
= (上证50 month_basis + 沪深300 month_basis + 中证500 month_basis + 中证1000 month_basis) / 4
```

规则：

- 只对当日存在的值求平均
- 如果 4 个都没有值，则写 `0`

### 5.3 breadth_up_count / breadth_total_count / breadth_up_pct

这 3 个字段 5 个指数共用同一份值，不需要按指数分别计算。

也就是说，同一个 `trade_date` 下，5 行记录的：

- `breadth_up_count`
- `breadth_total_count`
- `breadth_up_pct`

都应该相同。

#### 历史部分

历史部分使用：

`stock_daily_data` 且 `data_source = 'stock_zh_a_hist_tx'`

历史统计规则：

1. 以股票为粒度，比较“当日 `close_price`”与“前一交易日 `close_price`”
2. `当日 close_price > 前一交易日 close_price` 记为上涨
3. `当日有有效 close_price 且前一交易日也有有效 close_price` 的股票，计入总股票数

建议不要依赖历史数据中的：

- `pre_close_price`
- `price_change_amount`
- `price_change_rate`

因为历史回补来源里，这几个字段可能为空。

#### 最新交易日部分

最新交易日优先使用：

`stock_daily_data` 且 `data_source = 'stock_zh_a_spot'`

最新日统计规则：

1. 优先使用 `price_change_amount > 0` 判断上涨
2. 如果 `price_change_amount` 缺失，则回退到：

```text
(latest_price 或 close_price) - pre_close_price
```

3. 当日有有效行情的股票数，记为 `breadth_total_count`

#### 百分比公式

```text
breadth_up_pct = breadth_up_count / breadth_total_count * 100
```

规则：

- 如果 `breadth_total_count = 0`，则写 `0`

## 6. 数据侧实现顺序

### 6.1 backfill

需要提供一个全历史回补任务：

`backfill quant_index_dashboard_daily`

功能：

1. 全历史重算 `quant_index_dashboard_daily`
2. 每个交易日写入 5 条指数记录
3. 支持重复执行，重复执行时按 `(index_code, trade_date)` 覆盖更新

### 6.2 daily

需要提供一个日更任务：

`daily quant_index_dashboard_daily`

执行顺序要求：

1. 股票历史/快照数据已入库
2. 指数日线数据已入库
3. 连续合约期货数据已入库
4. 情绪指标数据已入库
5. 最后再执行 `quant_index_dashboard_daily` 最新交易日重算

说明：

- 本方案明确采用收盘后更新
- 不要求盘中实时
- 只需要保证收盘后一次更新稳定、完整即可

## 7. FIT 后续对接方式

### 7.1 对接原则

FIT 不通过跨服务 HTTP 向 `akshareProkect` 取数据，而是继续直接读共享 MySQL。

也就是说：

- 数据表由 `akshareProkect` 维护
- FIT 后端只负责读取这张预计算表并组装接口

### 7.2 FIT 后端新增接口

后续 FIT 后端建议新增一个只读聚合接口：

`GET /stocks/quant/index-dashboard?index_code=...&mode=recent|full`

参数：

- `index_code`：当前选中的指数代码
- `mode`：
  - `recent`
  - `full`

### 7.3 返回结构

返回结构固定包含：

- `index`
- `range_mode`
- `candles`
- `emotion_points`
- `basis_points`
- `breadth_points`

建议结构：

```json
{
  "index": {
    "code": "sh000001",
    "name": "上证指数"
  },
  "range_mode": "recent",
  "candles": [
    {
      "trade_date": "2026-03-27",
      "open": 0,
      "high": 0,
      "low": 0,
      "close": 0,
      "pre_close": 0,
      "change": 0,
      "pct_chg": 0,
      "vol": 0,
      "amount": 0,
      "pe_ttm": 0,
      "pb": 0,
      "total_market_value": 0,
      "circulating_market_value": 0
    }
  ],
  "emotion_points": [
    {
      "trade_date": "2026-03-27",
      "value": 63.5
    }
  ],
  "basis_points": [
    {
      "trade_date": "2026-03-27",
      "main_basis": -12.4,
      "month_basis": -8.1
    }
  ],
  "breadth_points": [
    {
      "trade_date": "2026-03-27",
      "up_count": 3120,
      "total_count": 5842,
      "up_ratio_pct": 53.4030
    }
  ]
}
```

要求：

- `candles` 继续从现有 `index_daily_data` 读取
- `emotion_points / basis_points / breadth_points` 统一从 `quant_index_dashboard_daily` 读取
- 不再分别现算

## 8. K 线与技术指标口径

本次只预计算以下 3 类辅助数据：

- 情绪指标
- 期现差
- 涨跌家数

以下内容不做数据库预计算：

- 指数 K 线
- MA
- BOLL
- MACD
- KDJ
- WR

原因：

1. 指数 K 线已经有现成数据源
2. 技术指标参数在前端是可调的，不适合做死表预计算

因此后续仍然保持：

- K 线：后端读取现有指数日线
- 技术指标：前端根据 `candles` 按用户参数本地计算

## 9. 前端指数页后续加载策略

后续 FIT 前端“量化展示 > 指数”页面建议改成两阶段加载。

### 9.1 首屏阶段

首屏只发两个请求：

1. `fetchIndexOptions()`
2. `GET /stocks/quant/index-dashboard?index_code=默认指数&mode=recent`

其中：

- `recent` 默认取最近 `750` 个交易日

### 9.2 首屏渲染后

页面先把 `recent` 数据渲染出来，用户能先看到最近阶段图表。

然后后台再发：

`GET /stocks/quant/index-dashboard?index_code=当前指数&mode=full`

把完整历史补齐。

要求：

- 后台补齐全量历史时，不要闪屏
- 不要重置用户当前视窗
- 不要因为补齐全量就把图表重新跳回最左边

### 9.3 切换指数

当用户快速切换指数时：

- 取消旧请求，或者忽略旧请求回包
- 只保留最后一次选择的结果落屏

## 10. 旧接口处理原则

以下旧接口先保留：

- `index-emotions`
- `index-futures-basis`
- `index-breadth`

但指数量化页主路径不再依赖它们。

原则：

1. 先保留旧接口，避免影响其他页面
2. 指数量化页优先切到新聚合接口
3. 其他页面是否后续迁移，再单独评估

## 11. 数据库侧验收 SQL

### 11.1 检查每个交易日是否有 5 条记录

```sql
SELECT
  trade_date,
  COUNT(*) AS row_count
FROM quant_index_dashboard_daily
GROUP BY trade_date
HAVING COUNT(*) <> 5;
```

期望：

- 结果为空

### 11.2 检查上证指数情绪是否等于四大指数同日平均

```sql
SELECT
  a.trade_date,
  a.emotion_value AS sse_emotion,
  b.avg_emotion AS core_avg_emotion
FROM quant_index_dashboard_daily a
JOIN (
  SELECT
    trade_date,
    AVG(emotion_value) AS avg_emotion
  FROM quant_index_dashboard_daily
  WHERE index_name IN ('上证50', '沪深300', '中证500', '中证1000')
  GROUP BY trade_date
) b
  ON a.trade_date = b.trade_date
WHERE a.index_name = '上证指数'
  AND ABS(a.emotion_value - b.avg_emotion) > 0.0001;
```

期望：

- 结果为空

### 11.3 检查上证指数期现差是否等于四大指数同日平均

```sql
SELECT
  a.trade_date,
  a.main_basis AS sse_main_basis,
  b.avg_main_basis,
  a.month_basis AS sse_month_basis,
  b.avg_month_basis
FROM quant_index_dashboard_daily a
JOIN (
  SELECT
    trade_date,
    AVG(main_basis) AS avg_main_basis,
    AVG(month_basis) AS avg_month_basis
  FROM quant_index_dashboard_daily
  WHERE index_name IN ('上证50', '沪深300', '中证500', '中证1000')
  GROUP BY trade_date
) b
  ON a.trade_date = b.trade_date
WHERE a.index_name = '上证指数'
  AND (
    ABS(a.main_basis - b.avg_main_basis) > 0.0001
    OR ABS(a.month_basis - b.avg_month_basis) > 0.0001
  );
```

期望：

- 结果为空

### 11.4 检查 breadth_up_pct 公式是否正确

```sql
SELECT
  trade_date,
  index_name,
  breadth_up_count,
  breadth_total_count,
  breadth_up_pct
FROM quant_index_dashboard_daily
WHERE breadth_total_count > 0
  AND ABS(
    breadth_up_pct - breadth_up_count / breadth_total_count * 100
  ) > 0.0001;
```

期望：

- 结果为空

## 12. FIT 侧验收标准

### 12.1 请求层

指数量化页首屏不再并发请求 4 组原始数据。

首屏应收敛为：

1. 指数选项
2. `index-dashboard(mode=recent)`

### 12.2 展示层

要求：

- 首屏先显示最近阶段数据
- 然后后台再补齐全量历史
- 悬停时能显示：
  - `上涨家数百分比`
  - `上涨家数 / 总数`

### 12.3 体验层

外网访问时，用户对“量化展示 > 指数”的体感速度应明显优于当前版本。

建议至少达到以下目标：

- 首屏先有图，不再长时间白屏
- 最近数据优先显示
- 切换指数时不再把浏览器长时间卡住

## 13. 建议落地顺序

推荐按以下顺序推进：

1. `akshareProkect` 新增 `quant_index_dashboard_daily` 表
2. `akshareProkect` 完成全历史回补任务
3. `akshareProkect` 完成收盘后日更任务
4. 用上面的验收 SQL 先验证数据表
5. FIT 后端新增 `GET /stocks/quant/index-dashboard`
6. FIT 前端指数页切到“recent + full”两阶段加载
7. 最后再决定旧接口是否继续给其他页面使用

## 14. 适用范围与假设

本方案基于以下假设：

1. 新增表、回补任务、日更任务都由 `akshareProkect` 实现。
2. FIT 和 `akshareProkect` 继续共用当前这套 MySQL。
3. 不新增中间服务，不通过跨服务 HTTP 传输这类汇总数据。
4. 第一版只优化“量化展示 > 指数”链路。
5. 首页、股票量化页、策略页的其他性能问题，不在本文档范围内一起处理。

## 15. 最终结论

这次的核心不是优化图表组件，而是把最重的 3 类辅助数据：

- 情绪指标
- 期现差
- 涨跌家数

从“运行时现算”改成“数据侧预计算”。

数据项目完成 `quant_index_dashboard_daily` 后，FIT 侧只需要：

1. 新增一个只读聚合接口
2. 把指数量化页切成 `recent -> full` 分阶段加载

就能把当前最明显的首屏慢问题压下去，而且还能让页面、策略回测和后续扩展共享同一套指标口径。
