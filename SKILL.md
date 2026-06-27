---
name: skill-tushare-servicehub-assistant
description: 通过 ServiceHub 中转统一获取 TuShare 的股票基础资料、行情、财务、主营业务和股权结构数据，并输出标准 JSON 结果。适用于执行 TuShare 标准测试用例、按自然语言完成股票分析场景、校验返回字段，或发起受控自定义 TuShare 查询。
disable-model-invocation: true
user-invocable: true
argument-hint: [natural-language request]
---

# TuShare ServiceHub 助手

## Goal

通过 ServiceHub 的 `/api/tushare/query` 中转接口，统一完成以下任务：

1. 执行内置 TuShare 标准测试用例。
2. 发起受控自定义 TuShare 查询。
3. 围绕行情、主营业务、财务、股权结构四类主场景组织查询与分析。
4. 先查本地业务仓库和缓存，再决定是否远程调用。
5. 输出兼容后续接口文档回写流程的标准 JSON 结果。

## Required Inputs

执行前至少确认以下输入：

1. ServiceHub 凭证。
   - 用户名
   - 密码或 passtoken
2. 任务目标。
   - 标准测试用例：提供 `case` 名称，或接口名，或中文任务名
   - 自定义查询：提供 `api_name` 和 `params`
   - 业务场景分析：提供股票代码、股票简称或上市公司名称
3. 可选时间范围。
   - 行情场景通常需要时间范围
   - 财务场景默认使用近三年加最近一期
   - 股权结构场景如需指定时点，再补 `period` 或 `ann_date`

默认 ServiceHub 地址固定为：

```text
https://www.ccailab.top
```

凭证读取优先级：

1. 命令行参数
2. 环境变量或 `.env`
3. `data/credentials.json`

优先环境变量：

- `TUSHARE_SERVICEHUB_USERNAME`
- `TUSHARE_SERVICEHUB_PASSTOKEN`
- `TUSHARE_SERVICEHUB_BASE_URL`

兼容环境变量：

- `SERVICEHUB_USERNAME`
- `SERVICEHUB_PASSTOKEN`
- `SERVICEHUB_BASE_URL`
- `SERVICETUBER_USERNAME`
- `SERVICETUBER_PASSTOKEN`
- `SERVICETUBER_BASE_URL`

## Workflow

1. 先判断用户意图属于哪一类。
   - `list-cases`
   - `run-case`
   - `custom-query`
   - `scenario-query`
   - `warehouse-query`
2. 如需补充接口约束、测试用例或场景规则，按需读取参考文件。
   - 接口约束：`references/api_spec.md`
   - 标准用例映射：`references/case_map.json`、`references/case_catalog.md`
   - 场景规则：`references/usage_scenarios.md`
   - 本地存储分层：`references/local_data_architecture.md`
   - 文档回写要求：`references/writeback_workflow.md`
3. 先识别最小可执行参数集合。
4. 如果关键参数缺失，只追问缺失项，不把整套参数列表抛给用户。
5. 如命中四个主场景之一，优先使用场景流程，而不是让用户自己记底层接口。
6. 查询策略默认按以下顺序执行。
   - 先查本地业务仓库
   - 再查接口缓存
   - 本地都缺失时再走 ServiceHub 远程查询
7. 只有在以下情况才优先远程。
   - 用户明确要求最新数据
   - 用户明确要求 `refresh`
   - 本地数据不足以完成当前场景
8. 调用统一脚本：

```bash
python scripts/tushare_tool.py <subcommand> [options]
```

9. 读取脚本返回 JSON。
10. 先给用户摘要，再补关键字段、结果路径和必要结构化结果。

## Decision Rules

### 1. 交互模式

这个技能包必须表现为“对话式单入口技能包”，而不是让用户自己记忆接口名、用例名和命令参数。

必须由技能包负责：

1. 识别用户意图。
2. 判断应该走标准用例、场景分析还是自定义查询。
3. 自动补齐可推断的参数。
4. 在缺少关键参数时主动追问。
5. 在需要确认的情况下先确认，再执行。

### 2. 最小必要补参机制

每类任务都先识别“最小可执行参数集合”，缺一项追问一项。

1. 市场行情
   - 最低参数：股票代码或公司名
   - 如时间范围缺失，优先使用用户上下文；仍无信息时追问
2. 主营业务
   - 最低参数：股票代码或公司名
3. 财务情况
   - 最低参数：股票代码或公司名
   - 默认周期：近三年加最近一期
4. 股权结构
   - 最低参数：股票代码或公司名
   - 如用户指定观察时点，再补 `period` 或 `ann_date`
5. 标准测试用例
   - 最低参数：`case`
6. 自定义查询
   - 最低参数：`api_name` 和 `params`

追问规则：

1. 每次只追问当前缺失的关键参数。
2. 能从上下文推断的内容直接补齐。
3. 不能可靠推断时，不要替用户擅自猜完整参数。

### 3. 标准用例优先

若用户需求落在以下接口范围内，优先走内置标准用例：

- `stock_basic`
- `stock_company`
- `income`
- `balancesheet`
- `cashflow`
- `forecast`
- `express`
- `fina_indicator`
- `fina_mainbz`
- `top10_holders`
- `top10_floatholders`
- `pledge_stat`
- `pledge_detail`
- `repurchase`
- `share_float`
- `block_trade`
- `stk_holdertrade`
- `stk_surv`

### 4. 场景路由

按以下规则识别四个主场景：

1. 用户提到“行情”“走势”“最近价格”“成交量”“估值”“市场表现”。
   - 走 `scenario-query --scenario market`
2. 用户提到“主营业务”“做什么业务”“业务构成”“收入来源”。
   - 走 `scenario-query --scenario business`
3. 用户提到“近三年财务”“利润表”“资产负债表”“现金流”“财务情况”。
   - 走 `scenario-query --scenario finance`
4. 用户提到“股权结构”“前十大股东”“流通股东”“质押”“增减持”。
   - 走 `scenario-query --scenario ownership`

### 5. 自定义查询边界

只有在以下情况才走 `custom-query`：

1. 用户明确指定了非内置接口。
2. 用户明确要求临时改写内置 case 的参数。
3. 用户明确表示不要标准测试结果，只要直接查数据。

若只是常规测试或常规场景分析，不要优先改走 `custom-query`。

### 6. 执行前确认

以下情况先确认，再执行：

1. 用户要求批量执行多个接口或多个用例。
2. 用户要求强制刷新远程数据。
3. 用户要求覆盖默认参数。
4. 用户要求高频或明显可能扣点较多的自定义查询。

### 7. 主场景分析模块

优先按以下四个场景组织分析流程：

1. 了解某一只股票的市场行情情况
   - 先确定股票标的和时间范围
   - 优先组合：`daily`、必要时补 `daily_basic`
2. 了解某一家上市公司的主营业务情况
   - 优先组合：`stock_basic`、`stock_company`、`fina_mainbz`
3. 基于近三年及最近一期的财务数据，了解某一只股票对应上市公司的财务情况
   - 优先组合：`income`、`balancesheet`、`cashflow`、`fina_indicator`
4. 了解某家上市公司的股权结构
   - 优先组合：`top10_holders`、`top10_floatholders`、`pledge_stat`、`pledge_detail`、`stk_holdertrade`

## Output Requirements

对用户输出时，不要先直接抛原始 JSON。默认输出顺序：

1. 先说明执行了什么。
2. 再给摘要结论。
3. 再给关键字段或关键指标。
4. 如有结果文件、积分余额、扣点或交易单号，再补这些信息。
5. 用户需要时再展开完整 JSON。

标准测试结果至少应保留：

1. `tc_id`
2. `request_data.api_name`
3. `steps[0].details.response_data.columns`
4. `steps[0].details.response_data.row_count`

场景查询优先使用以下字段对外表达：

1. `summary`
2. `report`
3. `analysis_text`

## Validation

执行后至少检查以下内容：

1. 凭证是否存在。
2. `run-case` 是否命中有效 case。
3. `custom-query` 是否提供 `api_name` 和 `params`。
4. 返回是否包含成功状态、业务结果和必要元信息。
5. 标准用例是否保留 `columns`、`row_count`、`records`。
6. 本地缓存是否命中；未命中时是否已写回缓存数据库。
7. 远程查询成功后，是否已写回本地业务仓库。
8. 场景查询是否返回 `summary`、`report` 或 `analysis_text` 中至少一种可读结果。

## Fallback

1. 如远程服务不可达，先排查 `https://www.ccailab.top` 网络连通性。
2. 如积分不足，直接告知用户，不要盲目重试。
3. 如信息不足，先补参，不要直接把底层报错原样抛给用户。
4. 如用户要求“先查本地，没有再远程”，默认就按该策略执行。
5. 如用户只允许本地读取，优先使用 `warehouse-query` 或 `--cache-only`。
6. 如场景所需本地数据不足，再说明缺口并建议是否远程补数。

## Examples

### 示例 1：执行标准测试用例

用户说：

```text
帮我跑一个 stock_basic 的 TuShare 测试用例
```

处理方式：

1. 识别为 `run-case`
2. 识别 `case=stock_basic`
3. 执行：

```bash
python scripts/tushare_tool.py run-case --case stock_basic
```

### 示例 2：列出可用用例

用户说：

```text
有哪些内置的 TuShare 用例
```

处理方式：

1. 识别为 `list-cases`
2. 执行：

```bash
python scripts/tushare_tool.py list-cases
```

### 示例 3：自定义查询

用户说：

```text
帮我通过 ServiceHub 查一个 daily，参数是 ts_code=000001.SZ，start_date=20260101，end_date=20260105
```

处理方式：

1. 识别为 `custom-query`
2. 整理 `api_name=daily`
3. 整理 `params`
4. 执行：

```bash
python scripts/tushare_tool.py custom-query --api-name daily --params '{"ts_code":"000001.SZ","start_date":"20260101","end_date":"20260105"}'
```

### 示例 4：行情场景

用户说：

```text
我想了解一下平安银行最近三个月的市场行情情况
```

处理方式：

1. 识别为 `scenario-query --scenario market`
2. 股票标的明确
3. 时间范围明确为最近三个月
4. 优先查本地，不足时再远程补数

### 示例 5：财务场景

用户说：

```text
帮我基于近三年及最近一期财务数据看一下贵州茅台的财务情况
```

处理方式：

1. 识别为 `scenario-query --scenario finance`
2. 默认周期直接使用近三年加最近一期
3. 组合执行 `income`、`balancesheet`、`cashflow`、`fina_indicator`
4. 优先查本地，不足时再远程补数
