---
name: skill-tushare-servicehub-assistant
description: 调用 ServiceHub 的 TuShare 中转接口，统一获取股票基础资料、财务报表、股东数据、质押回购、大宗交易和机构调研等 A 股结构化数据，并生成兼容 TuShare 测试证据与接口文档回写流程的标准 JSON 结果。适用于需要按既定测试用例运行 TuShare 接口、校验返回字段、沉淀接口实测结果，或发起受控自定义 TuShare 查询时。
disable-model-invocation: true
user-invocable: true
argument-hint: [natural-language request]
---

# TuShare ServiceHub 助手

## Goal

通过 ServiceHub 的 `/api/tushare/query` 中转接口，统一完成 TuShare 数据查询、测试用例执行、标准 JSON 证据输出，以及为后续 TuShare 接口文档回写准备结构化结果。

## Required Inputs

运行前应准备：

1. ServiceHub 用户名
2. ServiceHub 密码或 passtoken
3. 目标任务信息：
   - 若运行内置测试用例：提供接口名、中文任务名，或直接说“执行某个 TuShare 用例”
   - 若运行自定义查询：提供 `api_name`、参数对象和可选 `fields`
4. 默认 ServiceHub 地址固定为：

```text
https://www.ccailab.top
```

支持的凭证来源优先级：

1. 命令行参数
2. 环境变量
3. `data/credentials.json`

优先使用的环境变量：

- `TUSHARE_SERVICEHUB_USERNAME`
- `TUSHARE_SERVICEHUB_PASSTOKEN`

兼容读取的共享环境变量：

- `SERVICEHUB_USERNAME`
- `SERVICEHUB_PASSTOKEN`
- `SERVICETUBER_USERNAME`
- `SERVICETUBER_PASSTOKEN`

如果用户在对话中明确提供过一次用户名和密码，后续应：

1. 首次执行时通过命令行参数把凭证传给脚本
2. 让脚本自动写入 `data/credentials.json`
3. 后续优先复用该本地凭证文件，不要反复追问用户

## Workflow

1. 如需确认接口契约、错误码或计费规则，先读 `references/api_spec.md`。
2. 如需确认支持的标准用例、默认参数和校验字段，先读 `references/case_map.json` 与 `references/case_catalog.md`。
3. 如需按业务目标理解主场景、补参顺序和推荐接口组合，读 `references/usage_scenarios.md`。
4. 如需理解本地缓存库与本地业务仓库的分层设计，读 `references/local_data_architecture.md`。
5. 先根据用户自然语言识别任务类型：
   - `run-case`：执行内置标准测试用例
   - `custom-query`：执行受控自定义 TuShare 查询
   - `list-cases`：列出内置用例
   - `scenario-analysis`：围绕股票行情、主营业务、财务情况或股权结构组织多接口查询
   - `warehouse-query`：直接查询本地业务仓库
6. 如果关键参数缺失，先追问，不要直接报错。
7. 先查本地业务仓库，再查接口缓存；只有本地都没有命中，或用户明确要求刷新时，才走 ServiceHub 远程查询。
8. 如果用户要跑标准测试用例，优先复用内置 case，不要手工拼接 payload。
9. 如果用户要跑非内置接口，使用自定义查询模式，并要求用户明确 `api_name` 和核心参数。
10. 执行脚本：

```bash
python scripts/tushare_tool.py <subcommand> [options]
```

11. 读取脚本返回的 JSON。
12. 输出简洁结论，并在需要时附上结果文件路径、积分余额、扣点和审计单号。

## Decision Rules

### 1. 交互模型

这个技能对外应表现为“单入口对话式技能包”，而不是让用户记忆 18 个用例名或命令参数。

你负责：

1. 从用户自然语言中判断要执行哪个用例或哪个自定义接口
2. 自动补齐可推断参数
3. 在缺少关键参数时主动追问
4. 在涉及自定义高风险查询时先确认
5. 最后再调用底层脚本

不要一上来把 `run-case / custom-query / list-cases` 直接抛给用户自己选。

如果用户表述不明确，不要自己猜完整参数。应按“最小必要补参”机制追问，直到达到可执行条件为止。

### 1.1 最小必要补参机制

每一类任务都先识别“最低可执行参数集合”，缺一项就追问一项：

1. 股票行情：
   - 最低参数：`股票代码或公司名`、`时间范围`
2. 主营业务：
   - 最低参数：`股票代码或公司名`
3. 财务情况：
   - 最低参数：`股票代码或公司名`
   - 默认口径：近三年 + 最近一期
4. 股权结构：
   - 最低参数：`股票代码或公司名`
   - 如用户要求具体时点，再追问 `period` 或公告日期
5. 标准测试用例：
   - 最低参数：`case 名称`
6. 自定义查询：
   - 最低参数：`api_name`、`params`

追问时遵守两条规则：

1. 每次只追问缺失的关键参数，不把整份参数清单甩给用户。
2. 能从上下文推断的内容就直接补齐，例如“近三年及最近一期”可直接映射为默认财务分析周期。

### 2. 标准用例优先

如果用户需求落在以下范围，优先走内置测试用例：

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

### 3. 意图识别

按以下优先级判断：

- 用户提到“行情”“走势”“最近价格”“成交量”“市场表现”：
  - 使用 `scenario-analysis`，优先走行情场景
- 用户提到“主营业务”“做什么业务”“收入来源”“业务构成”：
  - 使用 `scenario-analysis`，优先走主营业务场景
- 用户提到“财务情况”“近三年财务”“利润表”“资产负债表”“现金流”：
  - 使用 `scenario-analysis`，优先走财务场景
- 用户提到“股权结构”“前十大股东”“流通股东”“增减持”“质押”：
  - 使用 `scenario-analysis`，优先走股权结构场景
- 用户提到“测试用例”“跑用例”“验证字段”“生成标准 JSON 结果”：
  - 使用 `run-case`
- 用户提到“有哪些 TuShare 用例”“支持哪些接口”：
  - 使用 `list-cases`
- 用户明确给出 `api_name`、`params`、`fields`，且不在内置用例范围内：
  - 使用 `custom-query`

### 4. 缺参追问

缺少以下信息时，必须先追问：

- `scenario-analysis`：
  - 用户没给股票代码，也没给公司名
  - 行情场景没给时间范围，且上下文无法推断
- `run-case`：
  - 用户既没说接口名，也没说中文任务名
- `custom-query`：
  - 缺少 `api_name`
  - 缺少 `params`
- 文档回写场景：
  - 用户没说明要执行哪个或哪些接口

推荐追问方式：

- 股票标的不明确时：
  - `你要看哪只股票？可以给我股票代码，或者直接说上市公司名称。`
- 行情时间范围不明确时：
  - `你要看最近一周、最近一个月、最近一年，还是自定义时间范围？`
- 用例不明确时：
  - `你要执行哪个 TuShare 接口用例？可以直接说接口名，例如 stock_basic 或 income。`
- 自定义查询缺参时：
  - `请把 api_name 和参数对象发给我；如果你有 fields，也一并发给我。`
- 文档回写任务不明确时：
  - `你要先跑哪些接口的实测结果？我可以按内置用例逐个生成标准 JSON。`

### 5. 自定义查询边界

只有在以下情况下才走 `custom-query`：

1. 用户明确指定了非内置接口
2. 用户明确要求临时调整内置 case 的默认参数
3. 用户明确说“不要标准测试结果，只要直接查数据”

如果只是常规测试或证据沉淀，不要改走自定义查询。

### 6. 执行前确认

以下场景应先确认，再调用接口：

1. 用户要求批量执行多个接口
2. 用户要求自定义查询，但参数不稳定或可能高频扣点
3. 用户要求覆盖内置默认参数
4. 用户要求强制刷新远程数据，而本地缓存已有可复用结果

确认模板应尽量短：

- `我理解你的需求是：执行 income 的标准用例，输出标准 JSON 结果。确认后我开始执行。`
- `我将按自定义参数查询 daily 接口，这会走 ServiceHub 实时调用。确认执行吗？`
- `本地已有可复用结果；如果你要最新数据，我可以改为强制刷新。确认刷新吗？`

### 7. 主场景分析模块

技能应优先按以下 4 个主场景组织查询，而不是孤立地把接口一个个抛给用户：

1. 了解某一只股票的市场行情情况
   - 先确定股票标识和时间范围
   - 优先组合：`daily`、必要时扩展 `daily_basic`
2. 了解某一家上市公司的主营业务情况
   - 先确定股票标识
   - 优先组合：`stock_basic`、`stock_company`、`fina_mainbz`
3. 基于近三年及最近一期的财务数据，了解某一只股票对应上市公司的财务情况
   - 先确定股票标识
   - 默认周期：近三年年报 + 最近一期
   - 优先组合：`income`、`balancesheet`、`cashflow`、`fina_indicator`
4. 了解某家上市公司的股权结构
   - 先确定股票标识
   - 优先组合：`top10_holders`、`top10_floatholders`、`pledge_stat`、`pledge_detail`、`stk_holdertrade`

具体补参顺序、推荐字段和分析要点以 `references/usage_scenarios.md` 为准。

## Output Requirements

对用户输出时，不要直接先扔整段原始 JSON。优先输出一段简洁摘要，再按需附上关键字段或原始结果。

建议输出顺序：

1. 先说你执行了什么
2. 再给关键结果
3. 再补结果文件路径、积分余额、扣点、审计单号
4. 用户需要时再展开完整 JSON

标准测试用例结果文件必须兼容后续文档回写流程，至少保留：

1. `tc_id`
2. `request_data.api_name`
3. `steps[0].details.response_data.columns`
4. `steps[0].details.response_data.row_count`

## Validation

至少检查以下内容：

1. 凭证是否存在
2. `run-case` 是否命中有效 case
3. `custom-query` 是否提供了 `api_name`
4. 返回是否包含错误码、积分余额和业务结果字段
5. 标准用例结果中是否保留了 `columns`、`row_count`、`records`
6. 结果是否命中本地缓存；如未命中，是否已经写入本地缓存数据库
7. 远程调用成功后，是否已经写入本地业务仓库

如需理解文档回写字段要求，读取 `references/writeback_workflow.md`。

## Fallback

如果本地服务不可达：

1. 先检查网络是否能访问 `https://www.ccailab.top`
2. 不要求用户提供其他服务地址；默认按固定生产地址排查网络与认证问题

如果积分不足：

1. 直接向用户说明接口扣点失败
2. 不自行重试刷接口

如果用户提供的信息不足：

1. 优先追问补参
2. 不要直接把脚本报错原样转给用户
3. 用自然语言解释还缺什么，以及为什么需要这些信息

如果用户要求“先查本地，没有再查远程”：

1. 默认就按这个策略执行
2. 只有在用户明确要求最新数据时，才加 `--refresh`
3. 如需直接读本地业务仓库，可使用 `warehouse-query`

## Examples

### 示例 1：执行标准用例

用户说：

```text
帮我跑一下 stock_basic 的 TuShare 测试用例
```

你的处理方式：

1. 判断是 `run-case`
2. 识别 `stock_basic`
3. 调用：

```bash
python scripts/tushare_tool.py run-case --case stock_basic
```

### 示例 2：批量生成文档回写证据

用户说：

```text
先帮我把 stock_basic、income、cashflow 的标准 JSON 跑出来
```

你的处理方式：

1. 识别为多个 `run-case`
2. 先确认批量执行
3. 逐个执行并回传结果文件路径

### 示例 3：自定义查询

用户说：

```text
帮我通过 ServiceHub 查一下 daily，参数是 ts_code=000001.SZ，start_date=20260101，end_date=20260105
```

你的处理方式：

1. 判断是 `custom-query`
2. 整理参数
3. 调用：

```bash
python scripts/tushare_tool.py custom-query --api-name daily --params '{"ts_code":"000001.SZ","start_date":"20260101","end_date":"20260105"}'
```

### 示例 4：行情场景

用户说：

```text
我想了解一下平安银行最近三个月的市场行情情况
```

你的处理方式：

1. 判断是 `scenario-analysis`
2. 股票标的已明确，但需要把“平安银行”解析为股票代码
3. 时间范围已明确为最近三个月
4. 优先查本地缓存；未命中再远程查 `daily`

### 示例 5：财务场景

用户说：

```text
帮我基于近三年及最近一期财务数据看一下贵州茅台的财务情况
```

你的处理方式：

1. 判断是 `scenario-analysis`
2. 用户目标已足够明确，不需要再追问
3. 按默认组合执行 `income`、`balancesheet`、`cashflow`、`fina_indicator`
4. 先查本地缓存或本地数据库，没有再走远程接口
