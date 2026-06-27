# 本地数据架构

技能包把本地数据分为两层：

## 1. 接口缓存层

- 文件：`data/tushare_cache.db`
- 作用：按 `api_name + params + fields` 缓存完整接口响应
- 目的：降低重复调用成本，支撑“先查本地，没有再远程”

## 2. 业务仓库层

- 文件：`data/tushare_warehouse.db`
- 作用：把成功返回的数据按业务域拆表保存，便于后续复用和本地查询

### 核心表

1. `companies`
2. `stock_basic_records`
3. `stock_company_records`
4. `market_daily`
5. `market_daily_basic`
6. `business_segments`
7. `financial_income`
8. `financial_balancesheet`
9. `financial_cashflow`
10. `financial_indicator`
11. `earnings_forecast`
12. `earnings_express`
13. `ownership_top10_holders`
14. `ownership_top10_floatholders`
15. `ownership_pledge_stat`
16. `ownership_pledge_detail`
17. `ownership_repurchase`
18. `ownership_share_float`
19. `ownership_block_trade`
20. `ownership_holder_trade`
21. `research_stk_surv`

## 默认查询策略

1. 先查业务仓库或缓存
2. 未命中再远程查询
3. 远程成功后同时回写缓存层和业务仓库层

## 命令支持

1. `run-case`：执行标准用例，并写入缓存层与业务仓库层
2. `custom-query`：执行自定义查询，并写入缓存层与业务仓库层
3. `warehouse-query`：按 `company / market / business / finance / ownership` 场景直接读取本地业务仓库
