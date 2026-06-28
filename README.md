# skill-tushare-servicehub-assistant

`skill-tushare-servicehub-assistant` 是一个下层基础技能包，用于通过 ServiceHub 统一访问 TuShare 数据，并承接“泛分析”和“事实分析”类需求。

它不是 18 个独立技能的集合，而是一个单入口技能包，负责：

1. 标准用例执行
2. 自定义查询
3. 本地缓存与本地仓库优先查询
4. 市场行情、主营业务、财务情况、股权结构等专题分析
5. 对模糊的上市公司分析需求进行默认承接

## 定位

这个技能的核心定位不是给出最终交易动作，而是：

1. 查数据
2. 查事实
3. 做泛分析
4. 做单专题分析
5. 为上层技能提供底座能力

因此，当用户说：

- `分析一下这家公司`
- `了解一下这家上市公司`
- `看看它的经营情况`
- `看看它的财务情况`
- `看看最近市场行情`
- `看看股权结构`

默认应先由本技能承接。

只有当用户明确要求以下内容时，才更适合切换到上层 `skill-stock-analysis`：

1. 投资建议
2. 买卖建议
3. 交易策略
4. 目标价
5. 止损位
6. 仓位建议
7. 多智能体分析

## 主场景

本技能当前重点支持四类分析场景：

1. 市场行情
2. 主营业务
3. 财务情况
4. 股权结构

## 数据策略

默认数据策略为：

1. 先查本地业务仓库 `data/tushare_warehouse.db`
2. 再查本地缓存 `data/tushare_cache.db`
3. 本地不足时再走 ServiceHub 远程查询
4. 远程查询成功后写回本地缓存和业务仓库

## 运行能力

统一通过：

```bash
python scripts/tushare_tool.py <subcommand> [options]
```

支持的典型能力包括：

1. `list-cases`
2. `run-case`
3. `custom-query`
4. `scenario-query`
5. `warehouse-query`

## 推荐触发示例

- `分析一下美心翼申这家公司`
- `帮我看一下平安银行最近三个月的市场行情`
- `帮我看一下宁德时代近三年及最近一期的财务情况`
- `帮我查一下这家上市公司的主营业务`
- `帮我看一下前十大股东和股权结构`
- `帮我跑一个 stock_basic 的标准用例`
- `给我一个 daily 的自定义查询结果`

## 与上层技能的关系

`skill-stock-analysis` 是上层决策技能，本技能是下层数据与泛分析技能。

区分原则：

1. 模糊公司分析需求，默认先走本技能
2. 明确投资建议或交易建议需求，再走 `skill-stock-analysis`

推荐目录结构：

```text
SKILLS-办公技能/
├─ skill-stock-analysis/
└─ skill-tushare-servicehub-assistant/
```

## 安装

```bash
git clone https://github.com/JasonCai2024/skill-tushare-servicehub-assistant.git
cd skill-tushare-servicehub-assistant
pip install -r requirements.txt
```
