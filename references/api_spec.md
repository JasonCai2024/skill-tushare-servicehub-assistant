# TuShare ServiceHub 接口说明

## 基本信息

- Base URL：`https://www.ccailab.top`
- 本地调试地址：`http://127.0.0.1:8000`
- 路径：`/api/tushare/query`
- 方法：`POST`

## 请求体

```json
{
  "username": "servicehub-user",
  "passtoken": "servicehub-pass",
  "api_name": "daily",
  "params": {
    "ts_code": "000001.SZ",
    "start_date": "20260101",
    "end_date": "20260105"
  },
  "fields": "ts_code,trade_date,open,high,low,close"
}
```

## 响应体关键字段

- `code`
- `message`
- `data.columns`
- `data.records`
- `bonus_points_balance`
- `recent_deducted_points`
- `trade_order_id`

## 错误码

- `401`：认证失败
- `402`：积分不足
- `422`：请求校验失败
- `502`：下游 TuShare 或网关异常

## 处理约束

1. 不要直连 TuShare 官方接口。
2. 不要在仓库中写入真实凭证。
3. ServiceHub 单次调用固定扣减 10 积分。
