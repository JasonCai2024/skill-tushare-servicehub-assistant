---
name: skill-tushare-servicehub-assistant
description: Uses ServiceHub as the single gateway for Tushare data access, local caching, warehouse-first lookup, standard test cases, controlled custom queries, and broad company / stock analysis scenarios such as market行情, business, finance, and ownership. This is the default lower-layer skill for generic listed-company analysis when the user is not explicitly asking for investment or trading advice.
disable-model-invocation: true
user-invocable: true
argument-hint: [natural-language request]
---

# TuShare ServiceHub Assistant

## Goal

Through ServiceHub `/api/tushare/query`, this skill provides a single entry point to:

1. Run built-in Tushare standard test cases
2. Execute controlled custom Tushare queries
3. Support broad listed-company analysis scenarios
4. Reuse local warehouse and cache first
5. Output structured results that can be reused downstream

## Primary Positioning

This is the lower-layer base skill for:

1. Data access
2. Factual company analysis
3. Single-topic analysis
4. Broad company understanding

It is the default choice when the user says things like:

- `分析一下这家公司`
- `了解一下这家上市公司`
- `看看它的财务情况`
- `看看最近行情`
- `看看主营业务`
- `看看股权结构`

It is not primarily a trading decision skill. If the user clearly wants buy/sell advice, target price, stop-loss, or multi-agent trading recommendation, route upward to `skill-stock-analysis`.

## Main Analysis Scenarios

This skill should prioritize the following scenarios:

1. 市场行情分析
2. 主营业务分析
3. 财务情况分析
4. 股权结构分析

These can be used independently or combined as broad factual analysis of a listed company.

## Required Inputs

Before execution, confirm at least:

1. ServiceHub credentials
2. Task type
3. Stock identifier or company name when needed
4. Time range only when the selected scenario requires it

Default ServiceHub base URL:

```text
https://www.ccailab.top
```

Credential lookup priority:

1. Command arguments
2. Environment variables or `.env`
3. `data/credentials.json`

Preferred environment variables:

- `TUSHARE_SERVICEHUB_USERNAME`
- `TUSHARE_SERVICEHUB_PASSTOKEN`
- `TUSHARE_SERVICEHUB_BASE_URL`

Compatible environment variables:

- `SERVICEHUB_USERNAME`
- `SERVICEHUB_PASSTOKEN`
- `SERVICEHUB_BASE_URL`
- `SERVICETUBER_USERNAME`
- `SERVICETUBER_PASSTOKEN`
- `SERVICETUBER_BASE_URL`

## Workflow

1. Identify the user's intent
2. Determine whether the task is:
   - `list-cases`
   - `run-case`
   - `custom-query`
   - `scenario-query`
   - `warehouse-query`
3. Build the minimum executable parameter set
4. Ask only for the missing critical parameter
5. Prefer local warehouse, then local cache, then remote ServiceHub
6. Only force remote refresh when the user explicitly requests latest data or `refresh`
7. Execute through:

```bash
python scripts/tushare_tool.py <subcommand> [options]
```

## Decision Rules

### 1. Default Routing Role

This skill is the default lower-layer skill when the user asks for broad company analysis without explicitly requesting investment advice.

Examples of requests that should default here:

1. `分析一下某某上市公司`
2. `了解一下这家公司`
3. `看看某只股票的基本情况`
4. `看看它近三年财务`
5. `看看它最近市场表现`

### 2. Escalation to Upper Skill

Route to `skill-stock-analysis` only when the user clearly asks for:

1. 投资建议
2. 买卖建议
3. 交易策略
4. 目标价
5. 止损位
6. 仓位建议
7. 多智能体分析
8. TradingAgents 风格决策报告

### 3. Minimum Follow-up

If the request is ambiguous, ask one minimal routing question:

`你是想了解公司的情况，还是想让我直接给出投资建议或交易建议？`

If the answer is still broad or factual, stay in this skill.

### 4. Scenario Routing

Map user intent as follows:

1. `行情 / 走势 / 最近价格 / 成交量 / 估值 / 市场表现`
   - use `scenario-query --scenario market`
2. `主营业务 / 做什么业务 / 业务构成 / 收入来源`
   - use `scenario-query --scenario business`
3. `近三年财务 / 利润表 / 资产负债表 / 现金流 / 财务情况`
   - use `scenario-query --scenario finance`
4. `股权结构 / 前十大股东 / 流通股东 / 质押 / 增减持`
   - use `scenario-query --scenario ownership`

### 5. Query Priority

Default execution order:

1. Local warehouse
2. Local cache
3. Remote ServiceHub

Use remote refresh first only when:

1. The user explicitly asks for latest data
2. The user explicitly asks for `refresh`
3. Local data is insufficient for the requested scenario

## Output Requirements

Do not dump raw JSON first.

Default output order:

1. Briefly explain what was executed
2. Give a summary conclusion
3. Show key fields or indicators
4. Mention result path or metadata if relevant
5. Expand to full JSON only when requested

Scenario queries should prefer:

1. `summary`
2. `report`
3. `analysis_text`

## Validation

After execution, verify at least:

1. Credentials exist
2. Requested case or API is valid
3. Return payload includes success status and business result
4. Standard cases retain columns and row count
5. Local cache or warehouse writeback happened when expected
6. Scenario queries return at least one readable output field

## Examples

### Example 1: Standard test case

`帮我跑一个 stock_basic 的 TuShare 测试用例`

### Example 2: List built-in cases

`有哪些内置的 TuShare 用例`

### Example 3: Custom query

`帮我通过 ServiceHub 查询 daily，ts_code=000001.SZ，start_date=20260101，end_date=20260105`

### Example 4: Broad company analysis

`分析一下美心翼申这家公司`

### Example 5: Finance scenario

`帮我基于近三年及最近一期财务数据看一下贵州茅台的财务情况`

### Example 6: Ownership scenario

`帮我看一下某家上市公司的股权结构和前十大股东`
