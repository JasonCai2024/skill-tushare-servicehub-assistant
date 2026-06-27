# INSTALL

## 安装步骤

1. 安装 Python 3.10+。
2. 进入技能根目录执行：

```bash
pip install -r requirements.txt
```

3. 配置以下环境变量，或复制 `.env.example` 为 `.env` 后填写：

- `TUSHARE_SERVICEHUB_USERNAME`
- `TUSHARE_SERVICEHUB_PASSTOKEN`
- 可选：`TUSHARE_SERVICEHUB_BASE_URL`

4. 运行示例：

```bash
python scripts/tushare_tool.py list-cases
python scripts/tushare_tool.py run-case --case stock_basic
python scripts/tushare_tool.py custom-query --api-name daily --params "{\"ts_code\":\"000001.SZ\",\"start_date\":\"20260101\",\"end_date\":\"20260105\"}"
python scripts/tushare_tool.py --refresh run-case --case stock_basic
python scripts/tushare_tool.py --cache-only custom-query --api-name daily --params "{\"ts_code\":\"000001.SZ\",\"start_date\":\"20260101\",\"end_date\":\"20260105\"}"
python scripts/tushare_tool.py warehouse-query --scenario company --identifier 平安银行
python scripts/tushare_tool.py scenario-query --scenario finance --identifier 贵州茅台
```

## 说明

1. 默认 ServiceHub 地址为 `https://www.ccailab.top`。
2. 标准用例结果默认输出到 `data/results/`。
3. 首次带凭证运行时，可加 `--save-credentials`，脚本会把凭证写入 `data/credentials.json`。
4. 查询缓存默认保存在 `data/tushare_cache.db`。
5. 规范化业务仓库默认保存在 `data/tushare_warehouse.db`。
