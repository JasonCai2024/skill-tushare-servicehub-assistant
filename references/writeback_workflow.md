# TuShare 接口文档回写规则

## 目标

将接口文档从“官网描述口径”收敛为“实测准确口径”，确保接口章节中的返回参数与真实测试结果一致。

## 标准结果文件必须保留的字段

1. `tc_id`
2. `request_data.api_name`
3. `steps[0].details.response_data.columns`
4. `steps[0].details.response_data.row_count`

## 回写原则

1. 只对已测试接口做回写。
2. 返回参数以实测 `columns` 为准。
3. 未测试接口保持原样。
4. 不额外保留临时测试痕迹说明。

## 建议流程

1. 先执行目标接口标准用例。
2. 在 `data/results/` 中收集每个接口最新一份结果文件。
3. 从结果中提取 `api_name` 与 `columns`。
4. 再回写主接口文档。
