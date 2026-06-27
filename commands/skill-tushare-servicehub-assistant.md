---
name: skill-tushare-servicehub-assistant
description: 通过 ServiceHub 中转执行 TuShare 标准用例、场景分析和自定义查询。适用于用户以自然语言提出股票行情、主营业务、财务情况、股权结构或 TuShare 接口验证需求时。
argument-hint: [natural-language request]
---

Use the skill at `~/.claude/skills/skill-tushare-servicehub-assistant/`.

Treat this as a single conversational skill package, not a command list that the user must memorize.

Preferred routing:

1. Map the user request to `list-cases`, `run-case`, `custom-query`, `scenario-query`, or `warehouse-query`.
2. Ask follow-up questions only for missing minimum-required parameters.
3. Prefer local warehouse first, then cache, then remote ServiceHub.
4. Confirm before batch runs, forced refresh, or expensive custom queries.
5. Prefer `summary`, `report`, and `analysis_text` as the first user-facing output.

Examples:

- `帮我跑一个 stock_basic 的测试用例`
- `帮我看一下平安银行最近三个月的市场行情`
- `帮我看一下贵州茅台近三年及最近一期的财务情况`
- `帮我查一个 daily，参数是 ts_code=000001.SZ，start_date=20260101，end_date=20260105`
