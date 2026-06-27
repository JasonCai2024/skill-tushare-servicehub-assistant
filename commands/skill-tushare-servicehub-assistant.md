---
description: 调用 ServiceHub 的 TuShare 中转接口，运行标准用例或自定义结构化查询。
argument-hint: [natural-language request]
---

Use the skill at `~/.claude/skills/skill-tushare-servicehub-assistant/`.

This is a conversational skill package, not a user-facing command list.

Preferred interaction model:

1. Infer whether the user wants `list-cases`, `run-case`, `custom-query`, `warehouse-query`, or a scenario-driven `scenario-query`.
2. Detect whether the user is actually asking one of the four business scenarios: market行情, 主营业务, 财务情况, 股权结构.
3. Prefer built-in standard cases whenever the request matches one of the 18 maintained TuShare cases.
4. Ask follow-up questions when the minimum required parameters are missing.
5. Prefer local warehouse first, then cache; only use remote refresh when the user asks for latest data or the local store misses.
6. Confirm before batch runs, forced refresh, or parameter overrides.
7. Then call the Python script.

When using `scenario-query` or `warehouse-query`, prefer the returned `summary` field as the first user-facing answer, and use the structured records as supporting detail.

Typical follow-up patterns:

- Missing case name:
  - `你要执行哪个 TuShare 接口用例？可以直接说 stock_basic、income 这种接口名。`
- Missing stock target:
  - `你要看哪只股票？可以给我股票代码，或者直接说上市公司名称。`
- Missing market range:
  - `你要看最近一周、最近一个月、最近一年，还是自定义时间范围？`
- Missing custom api_name:
  - `请把 api_name 发给我。`
- Missing custom params:
  - `请把 params 参数对象发给我，我再帮你发起 ServiceHub 查询。`
- Batch run:
  - `我将依次执行这几个标准用例，并输出结果文件路径。确认后我开始执行。`

Execution examples:

```bash
python ~/.claude/skills/skill-tushare-servicehub-assistant/scripts/tushare_tool.py list-cases
python ~/.claude/skills/skill-tushare-servicehub-assistant/scripts/tushare_tool.py --username "<ServiceHub用户名>" --passtoken "<ServiceHub密码>" --save-credentials run-case --case stock_basic
python ~/.claude/skills/skill-tushare-servicehub-assistant/scripts/tushare_tool.py run-case --case income
python ~/.claude/skills/skill-tushare-servicehub-assistant/scripts/tushare_tool.py --refresh run-case --case stock_basic
python ~/.claude/skills/skill-tushare-servicehub-assistant/scripts/tushare_tool.py custom-query --api-name daily --params '{"ts_code":"000001.SZ","start_date":"20260101","end_date":"20260105"}'
python ~/.claude/skills/skill-tushare-servicehub-assistant/scripts/tushare_tool.py warehouse-query --scenario finance --identifier "贵州茅台"
python ~/.claude/skills/skill-tushare-servicehub-assistant/scripts/tushare_tool.py scenario-query --scenario finance --identifier "贵州茅台"
```

Intent mapping:

- `我想了解一下平安银行最近三个月的市场行情` -> scenario analysis, resolve ticker, prefer cached `daily`, refresh only if needed
- `帮我看看贵州茅台近三年及最近一期的财务情况` -> scenario analysis, combine `income` + `balancesheet` + `cashflow` + `fina_indicator`
- `我想了解一下隆基绿能的股权结构` -> scenario analysis, combine `top10_holders` + `top10_floatholders` + `pledge_stat` + `pledge_detail` + `stk_holdertrade`
- `帮我跑一下 stock_basic 的测试用例` -> `run-case --case stock_basic`
- `有哪些内置的 TuShare 用例` -> `list-cases`
- `帮我查一下 daily，参数是 ...` -> `custom-query --api-name daily --params ...`
- `先把 stock_basic、income、cashflow 跑出来` -> multiple `run-case`

If the user provided credentials once in dialogue, pass them through `--username` and `--passtoken` on the first run. The script will persist them into `data/credentials.json` for later reuse.

Do not force the user to remember these command forms. They are implementation details for the assistant, not required user syntax.
