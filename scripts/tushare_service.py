#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Stable Python service API for upper-layer skills.

This module exposes a small, import-friendly API on top of
``tushare_tool.py`` so upper-layer skills can reuse the same
ServiceHub credentials, cache DB, warehouse DB, company resolution,
and auto-sync rules without invoking the CLI.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import tushare_tool as core


def _runtime(
    *,
    username: str = "",
    passtoken: str = "",
    base_url: str = "",
    credentials_file: str | Path | None = None,
) -> dict[str, Any]:
    credentials_path = Path(credentials_file).resolve() if credentials_file else core.DEFAULT_CREDENTIALS_PATH
    args = SimpleNamespace(
        username=username,
        passtoken=passtoken,
        base_url=base_url,
        save_credentials=False,
    )
    return core.resolve_runtime_config(args, credentials_path)


def _db_paths(
    *,
    cache_db: str | Path | None = None,
    warehouse_db: str | Path | None = None,
) -> tuple[Path, Path]:
    return (
        Path(cache_db).resolve() if cache_db else core.CACHE_DB_PATH.resolve(),
        Path(warehouse_db).resolve() if warehouse_db else core.WAREHOUSE_DB_PATH.resolve(),
    )


def _resolve_company_or_raise(
    identifier: str,
    *,
    username: str = "",
    passtoken: str = "",
    base_url: str = "",
    credentials_file: str | Path | None = None,
    cache_db: str | Path | None = None,
    warehouse_db: str | Path | None = None,
    refresh: bool = False,
    cache_only: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], Path, Path]:
    runtime = _runtime(
        username=username,
        passtoken=passtoken,
        base_url=base_url,
        credentials_file=credentials_file,
    )
    cache_db_path, warehouse_db_path = _db_paths(cache_db=cache_db, warehouse_db=warehouse_db)
    company, resolve_log = core.resolve_company_with_autofill(
        identifier,
        runtime,
        cache_db_path,
        warehouse_db_path,
        refresh=refresh,
        cache_only=cache_only,
    )
    if not company:
        raise ValueError(f"Unable to resolve company identifier: {identifier}")
    return company, resolve_log, runtime, cache_db_path, warehouse_db_path


def _query_and_record(
    api_name: str,
    params: dict[str, Any],
    *,
    fields: str = "",
    runtime: dict[str, Any],
    cache_db: Path,
    warehouse_db: Path,
    refresh: bool,
    cache_only: bool,
) -> dict[str, Any]:
    result = core.execute_query(
        api_name=api_name,
        params=params,
        fields=fields,
        runtime=runtime,
        cache_db=cache_db,
        warehouse_db=warehouse_db,
        refresh=refresh,
        cache_only=cache_only,
    )
    return {
        "api_name": api_name,
        "row_count": len(result["records"]),
        "cache": result["cache"],
        "warehouse": result["warehouse"],
        "records": result["records"],
        "columns": result["columns"],
    }


def query_api(
    api_name: str,
    params: dict[str, Any],
    *,
    fields: str = "",
    username: str = "",
    passtoken: str = "",
    base_url: str = "",
    credentials_file: str | Path | None = None,
    cache_db: str | Path | None = None,
    warehouse_db: str | Path | None = None,
    refresh: bool = False,
    cache_only: bool = False,
) -> dict[str, Any]:
    runtime = _runtime(
        username=username,
        passtoken=passtoken,
        base_url=base_url,
        credentials_file=credentials_file,
    )
    cache_db_path, warehouse_db_path = _db_paths(cache_db=cache_db, warehouse_db=warehouse_db)
    return core.execute_query(
        api_name=api_name,
        params=params,
        fields=fields,
        runtime=runtime,
        cache_db=cache_db_path,
        warehouse_db=warehouse_db_path,
        refresh=refresh,
        cache_only=cache_only,
    )


def resolve_company(
    identifier: str,
    *,
    username: str = "",
    passtoken: str = "",
    base_url: str = "",
    credentials_file: str | Path | None = None,
    cache_db: str | Path | None = None,
    warehouse_db: str | Path | None = None,
    refresh: bool = False,
    cache_only: bool = False,
) -> dict[str, Any]:
    company, resolve_log, _, _, _ = _resolve_company_or_raise(
        identifier,
        username=username,
        passtoken=passtoken,
        base_url=base_url,
        credentials_file=credentials_file,
        cache_db=cache_db,
        warehouse_db=warehouse_db,
        refresh=refresh,
        cache_only=cache_only,
    )
    return {
        "company": company,
        "resolve_log": resolve_log,
    }


def get_company_profile(
    identifier_or_ts_code: str,
    *,
    username: str = "",
    passtoken: str = "",
    base_url: str = "",
    credentials_file: str | Path | None = None,
    cache_db: str | Path | None = None,
    warehouse_db: str | Path | None = None,
    refresh: bool = False,
    cache_only: bool = False,
    latest_period: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    company, resolve_log, runtime, cache_db_path, warehouse_db_path = _resolve_company_or_raise(
        identifier_or_ts_code,
        username=username,
        passtoken=passtoken,
        base_url=base_url,
        credentials_file=credentials_file,
        cache_db=cache_db,
        warehouse_db=warehouse_db,
        refresh=refresh,
        cache_only=cache_only,
    )
    ts_code = company["ts_code"]
    sync_actions: list[dict[str, Any]] = []
    required_calls = [
        ("stock_basic", "stock_basic_records", {"ts_code": ts_code, "list_status": "L"}, ""),
        ("stock_company", "stock_company_records", {"ts_code": ts_code}, ""),
        ("fina_mainbz", "business_segments", {"ts_code": ts_code, "period": latest_period or core.latest_quarter_end(), "type": "P"}, ""),
    ]
    for api_name, table_name, params, fields in required_calls:
        if api_name == "fina_mainbz":
            need_sync = refresh or not core.warehouse_has_exact_rows(
                warehouse_db_path,
                table_name,
                ts_code,
                {"end_date": params["period"], "type": params["type"]},
            )
        else:
            need_sync = refresh or core.warehouse_row_count(warehouse_db_path, table_name, ts_code) == 0
        if cache_only and need_sync:
            sync_actions.append({"api_name": api_name, "status": "missing_local_data"})
            continue
        if not need_sync:
            continue
        sync_actions.append(
            _query_and_record(
                api_name,
                params,
                fields=fields,
                runtime=runtime,
                cache_db=cache_db_path,
                warehouse_db=warehouse_db_path,
                refresh=refresh,
                cache_only=cache_only,
            )
        )
    resolved_company = core.resolve_company_identifier(warehouse_db_path, ts_code) or company
    business_segments = core.fetch_warehouse_rows(warehouse_db_path, "business_segments", ts_code, "end_date", limit)
    report = core.build_business_report(resolved_company, business_segments, sync_actions)
    return {
        "ok": True,
        "scenario": "business",
        "identifier": identifier_or_ts_code,
        "company": resolved_company,
        "resolve_log": resolve_log,
        "sync_actions": sync_actions,
        "summary": core.summarize_business(resolved_company, business_segments),
        "report": report,
        "analysis_text": core.report_to_analysis_text(report),
        "business_segments": business_segments,
        "warehouse_db": str(warehouse_db_path),
        "cache_db": str(cache_db_path),
    }


def get_market_bundle(
    identifier_or_ts_code: str,
    *,
    start_date: str = "",
    end_date: str = "",
    days: int = 90,
    username: str = "",
    passtoken: str = "",
    base_url: str = "",
    credentials_file: str | Path | None = None,
    cache_db: str | Path | None = None,
    warehouse_db: str | Path | None = None,
    refresh: bool = False,
    cache_only: bool = False,
    limit: int = 120,
) -> dict[str, Any]:
    company, resolve_log, runtime, cache_db_path, warehouse_db_path = _resolve_company_or_raise(
        identifier_or_ts_code,
        username=username,
        passtoken=passtoken,
        base_url=base_url,
        credentials_file=credentials_file,
        cache_db=cache_db,
        warehouse_db=warehouse_db,
        refresh=refresh,
        cache_only=cache_only,
    )
    ts_code = company["ts_code"]
    final_end_date = end_date or core.today_ymd()
    final_start_date = start_date or (datetime.now(core.TZ) - timedelta(days=days)).strftime("%Y%m%d")
    sync_actions: list[dict[str, Any]] = []
    need_sync = refresh or not core.warehouse_has_market_window(
        warehouse_db_path,
        ts_code,
        final_start_date,
        final_end_date,
    )
    if cache_only and need_sync:
        sync_actions.append(
            {
                "status": "missing_local_data",
                "scenario": "market",
                "start_date": final_start_date,
                "end_date": final_end_date,
            }
        )
    elif need_sync:
        for api_name, fields in [
            ("daily", "ts_code,trade_date,open,high,low,close,vol,amount"),
            ("daily_basic", "ts_code,trade_date,close,turnover_rate,pe,pb,total_mv,circ_mv"),
        ]:
            sync_actions.append(
                _query_and_record(
                    api_name,
                    {"ts_code": ts_code, "start_date": final_start_date, "end_date": final_end_date},
                    fields=fields,
                    runtime=runtime,
                    cache_db=cache_db_path,
                    warehouse_db=warehouse_db_path,
                    refresh=refresh,
                    cache_only=cache_only,
                )
            )
    market_daily = core.fetch_warehouse_rows(warehouse_db_path, "market_daily", ts_code, "trade_date", limit)
    market_daily_basic = core.fetch_warehouse_rows(warehouse_db_path, "market_daily_basic", ts_code, "trade_date", limit)
    report = core.build_market_report(company, market_daily, market_daily_basic, sync_actions, final_start_date, final_end_date)
    return {
        "ok": True,
        "scenario": "market",
        "identifier": identifier_or_ts_code,
        "company": company,
        "resolve_log": resolve_log,
        "sync_actions": sync_actions,
        "summary": core.summarize_market(company, market_daily, market_daily_basic),
        "report": report,
        "analysis_text": core.report_to_analysis_text(report),
        "market_daily": market_daily,
        "market_daily_basic": market_daily_basic,
        "start_date": final_start_date,
        "end_date": final_end_date,
        "warehouse_db": str(warehouse_db_path),
        "cache_db": str(cache_db_path),
    }


def get_indicator_bundle(
    identifier_or_ts_code: str,
    *,
    end_date: str = "",
    lookback_days: int = 260,
    username: str = "",
    passtoken: str = "",
    base_url: str = "",
    credentials_file: str | Path | None = None,
    cache_db: str | Path | None = None,
    warehouse_db: str | Path | None = None,
    refresh: bool = False,
    cache_only: bool = False,
    limit: int = 320,
) -> dict[str, Any]:
    return get_market_bundle(
        identifier_or_ts_code,
        start_date=(datetime.now(core.TZ) - timedelta(days=lookback_days)).strftime("%Y%m%d"),
        end_date=end_date,
        username=username,
        passtoken=passtoken,
        base_url=base_url,
        credentials_file=credentials_file,
        cache_db=cache_db,
        warehouse_db=warehouse_db,
        refresh=refresh,
        cache_only=cache_only,
        limit=limit,
    )


def get_finance_bundle(
    identifier_or_ts_code: str,
    *,
    periods: list[str] | None = None,
    years: int = 3,
    username: str = "",
    passtoken: str = "",
    base_url: str = "",
    credentials_file: str | Path | None = None,
    cache_db: str | Path | None = None,
    warehouse_db: str | Path | None = None,
    refresh: bool = False,
    cache_only: bool = False,
    limit: int = 20,
) -> dict[str, Any]:
    company, resolve_log, runtime, cache_db_path, warehouse_db_path = _resolve_company_or_raise(
        identifier_or_ts_code,
        username=username,
        passtoken=passtoken,
        base_url=base_url,
        credentials_file=credentials_file,
        cache_db=cache_db,
        warehouse_db=warehouse_db,
        refresh=refresh,
        cache_only=cache_only,
    )
    ts_code = company["ts_code"]
    target_periods = periods or core.finance_periods(years)
    sync_actions: list[dict[str, Any]] = []
    for api_name, table_name in [
        ("income", "financial_income"),
        ("balancesheet", "financial_balancesheet"),
        ("cashflow", "financial_cashflow"),
        ("fina_indicator", "financial_indicator"),
    ]:
        missing = refresh or not core.warehouse_has_period_rows(
            warehouse_db_path,
            table_name,
            ts_code,
            "end_date",
            target_periods,
        )
        if not missing:
            continue
        for period in target_periods:
            if cache_only:
                sync_actions.append({"api_name": api_name, "period": period, "status": "missing_local_data"})
                continue
            result = _query_and_record(
                api_name,
                {"ts_code": ts_code, "period": period},
                runtime=runtime,
                cache_db=cache_db_path,
                warehouse_db=warehouse_db_path,
                refresh=refresh,
                cache_only=cache_only,
            )
            result["period"] = period
            sync_actions.append(result)
    income_rows = core.fetch_warehouse_rows(warehouse_db_path, "financial_income", ts_code, "end_date", limit)
    balancesheet_rows = core.fetch_warehouse_rows(warehouse_db_path, "financial_balancesheet", ts_code, "end_date", limit)
    cashflow_rows = core.fetch_warehouse_rows(warehouse_db_path, "financial_cashflow", ts_code, "end_date", limit)
    indicator_rows = core.fetch_warehouse_rows(warehouse_db_path, "financial_indicator", ts_code, "end_date", limit)
    report = core.build_finance_report(company, income_rows, indicator_rows, target_periods, sync_actions)
    return {
        "ok": True,
        "scenario": "finance",
        "identifier": identifier_or_ts_code,
        "company": company,
        "resolve_log": resolve_log,
        "target_periods": target_periods,
        "sync_actions": sync_actions,
        "summary": core.summarize_finance(company, income_rows, indicator_rows),
        "report": report,
        "analysis_text": core.report_to_analysis_text(report),
        "income": income_rows,
        "balancesheet": balancesheet_rows,
        "cashflow": cashflow_rows,
        "fina_indicator": indicator_rows,
        "warehouse_db": str(warehouse_db_path),
        "cache_db": str(cache_db_path),
    }


def get_cached_analysis_inputs(
    identifier_or_ts_code: str,
    *,
    scenario: str,
    **kwargs: Any,
) -> dict[str, Any]:
    if scenario == "market":
        return get_market_bundle(identifier_or_ts_code, **kwargs)
    if scenario == "indicator":
        return get_indicator_bundle(identifier_or_ts_code, **kwargs)
    if scenario == "finance":
        return get_finance_bundle(identifier_or_ts_code, **kwargs)
    if scenario == "company":
        return get_company_profile(identifier_or_ts_code, **kwargs)
    raise ValueError(f"Unsupported analysis scenario: {scenario}")


__all__ = [
    "query_api",
    "resolve_company",
    "get_company_profile",
    "get_market_bundle",
    "get_indicator_bundle",
    "get_finance_bundle",
    "get_cached_analysis_inputs",
]
