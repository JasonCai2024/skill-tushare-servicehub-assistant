#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""TuShare ServiceHub 助手命令行工具。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

try:
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv(usecwd=True))
except ImportError:
    pass


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
RESULT_DIR = DATA_DIR / "results"
CACHE_DB_PATH = DATA_DIR / "tushare_cache.db"
WAREHOUSE_DB_PATH = DATA_DIR / "tushare_warehouse.db"
DEFAULT_CREDENTIALS_PATH = DATA_DIR / "credentials.json"
CASE_MAP_PATH = REPO_ROOT / "references" / "case_map.json"
DEFAULT_BASE_URL = "https://www.ccailab.top"
TZ = ZoneInfo("Asia/Shanghai")

API_TABLE_MAP = {
    "stock_basic": ("stock_basic_records", ["ts_code"]),
    "stock_company": ("stock_company_records", ["ts_code"]),
    "daily": ("market_daily", ["ts_code", "trade_date"]),
    "daily_basic": ("market_daily_basic", ["ts_code", "trade_date"]),
    "income": ("financial_income", ["ts_code", "end_date", "ann_date"]),
    "balancesheet": ("financial_balancesheet", ["ts_code", "end_date", "ann_date"]),
    "cashflow": ("financial_cashflow", ["ts_code", "end_date", "ann_date"]),
    "fina_indicator": ("financial_indicator", ["ts_code", "end_date", "ann_date"]),
    "fina_mainbz": ("business_segments", ["ts_code", "end_date", "bz_item", "type"]),
    "forecast": ("earnings_forecast", ["ts_code", "ann_date", "end_date", "type"]),
    "express": ("earnings_express", ["ts_code", "ann_date", "end_date"]),
    "top10_holders": ("ownership_top10_holders", ["ts_code", "end_date", "holder_name"]),
    "top10_floatholders": ("ownership_top10_floatholders", ["ts_code", "end_date", "holder_name"]),
    "pledge_stat": ("ownership_pledge_stat", ["ts_code", "end_date"]),
    "pledge_detail": ("ownership_pledge_detail", ["ts_code", "ann_date", "holder_name"]),
    "repurchase": ("ownership_repurchase", ["ts_code", "ann_date", "proc"]),
    "share_float": ("ownership_share_float", ["ts_code", "ann_date", "float_date"]),
    "block_trade": ("ownership_block_trade", ["ts_code", "trade_date", "price", "vol"]),
    "stk_holdertrade": ("ownership_holder_trade", ["ts_code", "ann_date", "holder_name", "in_de"]),
    "stk_surv": ("research_stk_surv", ["ts_code", "surv_date"]),
}


def now_text() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def now_file_ts() -> str:
    return datetime.now(TZ).strftime("%Y%m%d_%H%M")


def today_ymd() -> str:
    return datetime.now(TZ).strftime("%Y%m%d")


def normalize_ts_code(identifier: str) -> str:
    value = identifier.strip().upper()
    if "." in value:
        if value.endswith(".SS"):
            return value[:-3] + ".SH"
        return value
    if value.isdigit() and len(value) == 6:
        if value.startswith(("60", "68", "90")):
            return f"{value}.SH"
        if value.startswith(("83", "43", "87")):
            return f"{value}.BJ"
        return f"{value}.SZ"
    return value


def latest_quarter_end(reference: datetime | None = None) -> str:
    now = reference or datetime.now(TZ)
    year = now.year
    month = now.month
    if month <= 3:
        return f"{year - 1}1231"
    if month <= 6:
        return f"{year}0331"
    if month <= 9:
        return f"{year}0630"
    return f"{year}0930"


def annual_periods(years: int, reference: datetime | None = None) -> list[str]:
    now = reference or datetime.now(TZ)
    latest_full_year = now.year - 1
    return [f"{latest_full_year - offset}1231" for offset in range(years - 1, -1, -1)]


def finance_periods(years: int) -> list[str]:
    periods = annual_periods(years)
    latest = latest_quarter_end()
    if latest not in periods:
        periods.append(latest)
    return periods


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def normalize_db_value(value: Any) -> Any:
    if value is None or isinstance(value, (int, float, str)):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def load_credentials(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = load_json(path)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def save_credentials(path: Path, username: str, passtoken: str, base_url: str) -> None:
    payload = {
        "servicehub": {
            "username": username,
            "passtoken": passtoken,
            "base_url": base_url,
        }
    }
    save_json(path, payload)


def first_non_empty(*values: str) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def resolve_runtime_config(args: argparse.Namespace, credentials_path: Path) -> dict[str, Any]:
    file_payload = load_credentials(credentials_path)
    servicehub_file = file_payload.get("servicehub", {}) if isinstance(file_payload.get("servicehub"), dict) else {}

    base_url = first_non_empty(
        args.base_url,
        os.getenv("TUSHARE_SERVICEHUB_BASE_URL", ""),
        os.getenv("SERVICEHUB_BASE_URL", ""),
        os.getenv("SERVICETUBER_BASE_URL", ""),
        str(servicehub_file.get("base_url", "")),
        DEFAULT_BASE_URL,
    )
    username = first_non_empty(
        args.username,
        os.getenv("TUSHARE_SERVICEHUB_USERNAME", ""),
        os.getenv("SERVICEHUB_USERNAME", ""),
        os.getenv("SERVICETUBER_USERNAME", ""),
        str(servicehub_file.get("username", "")),
    )
    passtoken = first_non_empty(
        args.passtoken,
        os.getenv("TUSHARE_SERVICEHUB_PASSTOKEN", ""),
        os.getenv("SERVICEHUB_PASSTOKEN", ""),
        os.getenv("SERVICETUBER_PASSTOKEN", ""),
        str(servicehub_file.get("passtoken", "")),
    )

    should_persist = bool(args.save_credentials or args.username or args.passtoken)
    if should_persist and username and passtoken:
        save_credentials(credentials_path, username, passtoken, base_url)

    return {
        "base_url": base_url.rstrip("/"),
        "username": username,
        "passtoken": passtoken,
        "credentials_path": str(credentials_path),
        "credentials_loaded_from_file": credentials_path.exists(),
        "credentials_persisted": should_persist,
    }


def ensure_credentials(config: dict[str, Any]) -> None:
    missing: list[str] = []
    if not config["username"]:
        missing.append("username")
    if not config["passtoken"]:
        missing.append("passtoken")
    if missing:
        raise ValueError(
            "缺少 ServiceHub 凭证：" + ", ".join(missing) + "。请通过命令行参数、环境变量或 data/credentials.json 提供。"
        )


def load_case_map() -> list[dict[str, Any]]:
    payload = load_json(CASE_MAP_PATH)
    if not isinstance(payload, list):
        raise ValueError("case_map.json 格式错误，应为数组。")
    return payload


def ensure_cache_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_cache (
                cache_key TEXT PRIMARY KEY,
                api_name TEXT NOT NULL,
                params_json TEXT NOT NULL,
                fields TEXT NOT NULL,
                response_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_api_cache_api_name
            ON api_cache (api_name)
            """
        )
        conn.commit()


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def ensure_warehouse_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS companies (
                ts_code TEXT PRIMARY KEY,
                symbol TEXT,
                name TEXT,
                area TEXT,
                industry TEXT,
                market TEXT,
                list_status TEXT,
                list_date TEXT,
                delist_date TEXT,
                cnspell TEXT,
                exchange TEXT,
                com_name TEXT,
                chairman TEXT,
                manager TEXT,
                secretary TEXT,
                reg_capital TEXT,
                setup_date TEXT,
                province TEXT,
                city TEXT,
                introduction TEXT,
                website TEXT,
                email TEXT,
                office TEXT,
                employees TEXT,
                main_business TEXT,
                business_scope TEXT,
                source_api TEXT,
                fetched_at TEXT,
                updated_at TEXT,
                payload_json TEXT
            )
            """
        )
        conn.commit()


def ensure_dynamic_table(
    conn: sqlite3.Connection,
    table_name: str,
    dynamic_columns: list[str],
) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {quote_ident(table_name)} (
            row_key TEXT PRIMARY KEY,
            ts_code TEXT,
            source_api TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )
    existing = {
        row[1]
        for row in conn.execute(f"PRAGMA table_info({quote_ident(table_name)})")
    }
    for column in dynamic_columns:
        if column not in existing:
            conn.execute(
                f"ALTER TABLE {quote_ident(table_name)} ADD COLUMN {quote_ident(column)} TEXT"
            )


def build_row_key(row: dict[str, Any], key_columns: list[str]) -> str:
    key_parts = []
    for column in key_columns:
        value = row.get(column)
        if value is not None and str(value).strip():
            key_parts.append(f"{column}={value}")
    if key_parts:
        return "|".join(key_parts)
    return hashlib.sha1(canonical_json(row).encode("utf-8")).hexdigest()


def upsert_rows_to_table(
    conn: sqlite3.Connection,
    table_name: str,
    api_name: str,
    rows: list[dict[str, Any]],
    key_columns: list[str],
    fetched_at: str,
) -> int:
    if not rows:
        return 0
    dynamic_columns = sorted({key for row in rows for key in row.keys()})
    ensure_dynamic_table(conn, table_name, dynamic_columns)
    count = 0
    for row in rows:
        row_key = build_row_key(row, key_columns)
        columns = ["row_key", "ts_code", "source_api", "fetched_at", "updated_at", "payload_json"] + dynamic_columns
        values = [
            row_key,
            row.get("ts_code"),
            api_name,
            fetched_at,
            fetched_at,
            json.dumps(row, ensure_ascii=False, sort_keys=True),
        ] + [normalize_db_value(row.get(column)) for column in dynamic_columns]
        placeholders = ", ".join("?" for _ in columns)
        update_clause = ", ".join(
            [f"{quote_ident(column)} = excluded.{quote_ident(column)}" for column in columns[1:]]
        )
        conn.execute(
            f"""
            INSERT INTO {quote_ident(table_name)} ({", ".join(quote_ident(column) for column in columns)})
            VALUES ({placeholders})
            ON CONFLICT(row_key) DO UPDATE SET
            {update_clause}
            """,
            values,
        )
        count += 1
    return count


def upsert_company_profiles(
    conn: sqlite3.Connection,
    api_name: str,
    rows: list[dict[str, Any]],
    fetched_at: str,
) -> int:
    count = 0
    for row in rows:
        ts_code = row.get("ts_code")
        if not ts_code:
            continue
        current = conn.execute(
            "SELECT payload_json FROM companies WHERE ts_code = ?",
            (ts_code,),
        ).fetchone()
        merged = {}
        if current and current[0]:
            try:
                merged = json.loads(current[0])
            except Exception:
                merged = {}
        merged.update({k: v for k, v in row.items() if v not in (None, "")})
        values = {
            "ts_code": ts_code,
            "symbol": merged.get("symbol"),
            "name": merged.get("name"),
            "area": merged.get("area"),
            "industry": merged.get("industry"),
            "market": merged.get("market"),
            "list_status": merged.get("list_status"),
            "list_date": merged.get("list_date"),
            "delist_date": merged.get("delist_date"),
            "cnspell": merged.get("cnspell"),
            "exchange": merged.get("exchange"),
            "com_name": merged.get("com_name"),
            "chairman": merged.get("chairman"),
            "manager": merged.get("manager"),
            "secretary": merged.get("secretary"),
            "reg_capital": normalize_db_value(merged.get("reg_capital")),
            "setup_date": merged.get("setup_date"),
            "province": merged.get("province"),
            "city": merged.get("city"),
            "introduction": merged.get("introduction"),
            "website": merged.get("website"),
            "email": merged.get("email"),
            "office": merged.get("office"),
            "employees": normalize_db_value(merged.get("employees")),
            "main_business": merged.get("main_business"),
            "business_scope": merged.get("business_scope"),
            "source_api": api_name,
            "fetched_at": fetched_at,
            "updated_at": fetched_at,
            "payload_json": json.dumps(merged, ensure_ascii=False, sort_keys=True),
        }
        columns = list(values.keys())
        placeholders = ", ".join("?" for _ in columns)
        update_clause = ", ".join(
            [f"{quote_ident(column)} = excluded.{quote_ident(column)}" for column in columns[1:]]
        )
        conn.execute(
            f"""
            INSERT INTO companies ({", ".join(quote_ident(column) for column in columns)})
            VALUES ({placeholders})
            ON CONFLICT(ts_code) DO UPDATE SET
            {update_clause}
            """,
            [values[column] for column in columns],
        )
        count += 1
    return count


def store_in_warehouse(
    db_path: Path,
    api_name: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    ensure_warehouse_db(db_path)
    fetched_at = now_text()
    table_name, key_columns = API_TABLE_MAP.get(api_name, (f"api_{api_name}", []))
    with sqlite3.connect(db_path) as conn:
        row_count = upsert_rows_to_table(conn, table_name, api_name, rows, key_columns, fetched_at)
        company_count = 0
        if api_name in {"stock_basic", "stock_company"}:
            company_count = upsert_company_profiles(conn, api_name, rows, fetched_at)
        conn.commit()
    return {
        "table": table_name,
        "rows_upserted": row_count,
        "companies_upserted": company_count,
        "db_path": str(db_path.resolve()),
    }


def resolve_company_identifier(db_path: Path, identifier: str) -> dict[str, Any] | None:
    ensure_warehouse_db(db_path)
    identifier = identifier.strip()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        if "." in identifier:
            row = conn.execute(
                "SELECT * FROM companies WHERE ts_code = ?",
                (identifier,),
            ).fetchone()
            return dict(row) if row else None
        row = conn.execute(
            """
            SELECT * FROM companies
            WHERE symbol = ?
               OR name = ?
               OR com_name = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (identifier, identifier, identifier),
        ).fetchone()
        if row:
            return dict(row)
        row = conn.execute(
            """
            SELECT * FROM companies
            WHERE name LIKE ? OR com_name LIKE ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (f"%{identifier}%", f"%{identifier}%"),
        ).fetchone()
        return dict(row) if row else None


def enrich_company_profile(db_path: Path, company: dict[str, Any] | None) -> dict[str, Any] | None:
    if not company:
        return None
    ts_code = company.get("ts_code")
    if not ts_code:
        return company
    latest = resolve_company_identifier(db_path, ts_code)
    if not latest:
        return company
    merged = dict(latest)
    merged.update({k: v for k, v in company.items() if v not in (None, "")})
    return merged


def resolve_company_with_autofill(
    identifier: str,
    runtime: dict[str, Any],
    cache_db: Path,
    warehouse_db: Path,
    refresh: bool,
    cache_only: bool,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    sync_log: list[dict[str, Any]] = []
    company = enrich_company_profile(warehouse_db, resolve_company_identifier(warehouse_db, identifier))
    if company and not refresh:
        return company, sync_log

    normalized = normalize_ts_code(identifier)
    candidate_queries: list[tuple[str, dict[str, Any], str]] = []
    if "." in normalized:
        candidate_queries.append(("stock_basic", {"ts_code": normalized, "list_status": "L"}, ""))
        candidate_queries.append(("stock_company", {"ts_code": normalized}, ""))
    else:
        candidate_queries.append(("stock_basic", {"name": identifier, "list_status": "L"}, ""))

    for api_name, params, fields in candidate_queries:
        try:
            result = execute_query(
                api_name=api_name,
                params=params,
                fields=fields,
                runtime=runtime,
                cache_db=cache_db,
                warehouse_db=warehouse_db,
                refresh=refresh,
                cache_only=cache_only,
            )
            sync_log.append(
                {
                    "api_name": api_name,
                    "row_count": len(result["records"]),
                    "cache": result["cache"],
                    "warehouse": result["warehouse"],
                }
            )
        except Exception as exc:
            sync_log.append({"api_name": api_name, "error": str(exc)})
            continue
        company = enrich_company_profile(
            warehouse_db,
            resolve_company_identifier(warehouse_db, identifier) or resolve_company_identifier(warehouse_db, normalized),
        )
        if company:
            return company, sync_log
    return company, sync_log


def fetch_warehouse_rows(
    db_path: Path,
    table_name: str,
    ts_code: str,
    order_column: str,
    limit: int,
) -> list[dict[str, Any]]:
    ensure_warehouse_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        if not table_exists:
            return []
        rows = conn.execute(
            f"""
            SELECT * FROM {quote_ident(table_name)}
            WHERE ts_code = ?
            ORDER BY {quote_ident(order_column)} DESC, updated_at DESC
            LIMIT ?
            """,
            (ts_code, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def warehouse_has_period_rows(
    db_path: Path,
    table_name: str,
    ts_code: str,
    period_column: str,
    periods: list[str],
) -> bool:
    ensure_warehouse_db(db_path)
    if not periods:
        return True
    with sqlite3.connect(db_path) as conn:
        table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        if not table_exists:
            return False
        placeholders = ", ".join("?" for _ in periods)
        rows = conn.execute(
            f"""
            SELECT DISTINCT {quote_ident(period_column)}
            FROM {quote_ident(table_name)}
            WHERE ts_code = ? AND {quote_ident(period_column)} IN ({placeholders})
            """,
            [ts_code] + periods,
        ).fetchall()
        existing = {row[0] for row in rows}
        return all(period in existing for period in periods)


def warehouse_has_market_window(
    db_path: Path,
    ts_code: str,
    start_date: str,
    end_date: str,
) -> bool:
    ensure_warehouse_db(db_path)
    with sqlite3.connect(db_path) as conn:
        table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'market_daily'",
        ).fetchone()
        if not table_exists:
            return False
        row = conn.execute(
            """
            SELECT MIN(trade_date), MAX(trade_date), COUNT(1)
            FROM market_daily
            WHERE ts_code = ? AND trade_date BETWEEN ? AND ?
            """,
            (ts_code, start_date, end_date),
        ).fetchone()
        if not row or row[2] == 0:
            return False
        min_date, max_date, count = row
        if not (min_date and max_date and min_date <= start_date and count >= 5):
            return False
        max_dt = datetime.strptime(str(max_date), "%Y%m%d")
        end_dt = datetime.strptime(str(end_date), "%Y%m%d")
        return max_dt >= (end_dt - timedelta(days=3))


def infer_market_window(daily_rows: list[dict[str, Any]], daily_basic_rows: list[dict[str, Any]]) -> tuple[str, str]:
    trade_dates = [
        str(row.get("trade_date"))
        for row in [*daily_rows, *daily_basic_rows]
        if row.get("trade_date")
    ]
    if not trade_dates:
        return "-", "-"
    return min(trade_dates), max(trade_dates)


def warehouse_row_count(
    db_path: Path,
    table_name: str,
    ts_code: str,
) -> int:
    ensure_warehouse_db(db_path)
    with sqlite3.connect(db_path) as conn:
        table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        if not table_exists:
            return 0
        row = conn.execute(
            f"SELECT COUNT(1) FROM {quote_ident(table_name)} WHERE ts_code = ?",
            (ts_code,),
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else 0


def warehouse_has_exact_rows(
    db_path: Path,
    table_name: str,
    ts_code: str,
    filters: dict[str, Any],
) -> bool:
    ensure_warehouse_db(db_path)
    with sqlite3.connect(db_path) as conn:
        table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        if not table_exists:
            return False
        clauses = ["ts_code = ?"]
        values: list[Any] = [ts_code]
        for key, value in filters.items():
            clauses.append(f"{quote_ident(key)} = ?")
            values.append(value)
        where_sql = " AND ".join(clauses)
        row = conn.execute(
            f"SELECT COUNT(1) FROM {quote_ident(table_name)} WHERE {where_sql}",
            values,
        ).fetchone()
        return bool(row and row[0] and int(row[0]) > 0)


def build_cache_key(api_name: str, params: dict[str, Any], fields: str) -> str:
    return f"{api_name}|{canonical_json(params)}|{fields.strip()}"


def get_cached_response(
    db_path: Path,
    api_name: str,
    params: dict[str, Any],
    fields: str,
) -> tuple[str, dict[str, Any]] | tuple[None, None]:
    ensure_cache_db(db_path)
    cache_key = build_cache_key(api_name, params, fields)
    with sqlite3.connect(db_path) as conn, closing(
        conn.execute(
            "SELECT response_json FROM api_cache WHERE cache_key = ?",
            (cache_key,),
        )
    ) as cursor:
        row = cursor.fetchone()
    if not row:
        return None, None
    return cache_key, json.loads(row[0])


def upsert_cached_response(
    db_path: Path,
    api_name: str,
    params: dict[str, Any],
    fields: str,
    response_body: dict[str, Any],
) -> str:
    ensure_cache_db(db_path)
    cache_key = build_cache_key(api_name, params, fields)
    now = now_text()
    payload = (
        cache_key,
        api_name,
        canonical_json(params),
        fields.strip(),
        json.dumps(response_body, ensure_ascii=False),
        now,
        now,
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO api_cache (
                cache_key, api_name, params_json, fields, response_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                response_json = excluded.response_json,
                updated_at = excluded.updated_at
            """,
            payload,
        )
        conn.commit()
    return cache_key


def build_case_indexes(cases: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_short_name = {str(item["short_name"]): item for item in cases}
    by_title_cn = {str(item["title_cn"]): item for item in cases}
    return by_short_name, by_title_cn


def resolve_case(case_name: str, cases: list[dict[str, Any]]) -> dict[str, Any]:
    by_short_name, by_title_cn = build_case_indexes(cases)
    case_name = case_name.strip()
    if case_name in by_short_name:
        return by_short_name[case_name]
    if case_name in by_title_cn:
        return by_title_cn[case_name]
    raise KeyError(f"未找到用例：{case_name}")


def make_post_request(url: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    response = requests.post(url, json=payload, timeout=180)
    try:
        body = response.json()
    except Exception:
        body = {"raw_text": response.text}
    return response.status_code, body


def execute_query(
    *,
    api_name: str,
    params: dict[str, Any],
    fields: str,
    runtime: dict[str, Any],
    cache_db: Path,
    warehouse_db: Path,
    refresh: bool,
    cache_only: bool,
) -> dict[str, Any]:
    payload = {
        "username": runtime["username"],
        "passtoken": runtime["passtoken"],
        "api_name": api_name,
        "params": params,
        "fields": fields,
    }
    url = f"{runtime['base_url']}/api/tushare/query"
    cache_hit = False
    cache_key = None
    warehouse_info = None
    body = None
    http_status = None

    if not refresh:
        cache_key, cached_body = get_cached_response(cache_db, api_name, params, fields)
        if cached_body is not None:
            body = cached_body
            http_status = 200
            cache_hit = True

    if body is None:
        if cache_only:
            raise ValueError("本地缓存未命中，且当前为 cache-only 模式。")
        ensure_credentials(runtime)
        http_status, body = make_post_request(url, payload)
        if http_status != 200:
            raise ValueError(f"ServiceHub HTTP {http_status}: {body}")
        if body.get("code") != 200:
            raise ValueError(f"ServiceHub body code {body.get('code')}: {body.get('message')}")
        cache_key = upsert_cached_response(cache_db, api_name, params, fields, body)

    data = body.get("data", {})
    columns = list(data.get("columns", []))
    raw_records = list(data.get("records", []))
    records = to_row_dicts(columns, raw_records)
    if http_status == 200 and body.get("code") == 200:
        warehouse_info = store_in_warehouse(warehouse_db, api_name, records)
    return {
        "api_name": api_name,
        "params": params,
        "fields": fields,
        "http_status": http_status,
        "body": body,
        "columns": columns,
        "raw_records": raw_records,
        "records": records,
        "cache": {
            "hit": cache_hit,
            "cache_key": cache_key,
            "db_path": str(cache_db.resolve()),
        },
        "warehouse": warehouse_info,
    }


def to_row_dicts(columns: list[str], records: list[list[Any]]) -> list[dict[str, Any]]:
    return [dict(zip(columns, row)) for row in records]


def build_checkpoints(case_cfg: dict[str, Any], response_data: dict[str, Any], error: str | None, http_status: int | None) -> list[dict[str, Any]]:
    columns = response_data.get("columns", [])
    row_count = response_data.get("row_count", -1)
    records = response_data.get("records", [])
    required_columns = case_cfg.get("required_columns", [])
    key_columns = case_cfg.get("key_columns", [])
    min_rows = int(case_cfg.get("min_rows", 0))

    checkpoints: list[dict[str, Any]] = []
    cp1_ok = error is None and isinstance(columns, list) and isinstance(records, list)
    checkpoints.append(
        {
            "name": "CP1_接口调用成功并返回标准结构",
            "status": "PASS" if cp1_ok else "FAIL",
            "detail": {"error": error, "http_status": http_status},
        }
    )

    missing_columns = [item for item in required_columns if item not in columns] if cp1_ok else required_columns
    cp2_ok = cp1_ok and not missing_columns
    checkpoints.append(
        {
            "name": "CP2_必备字段存在",
            "status": "PASS" if cp2_ok else "FAIL",
            "detail": {"required_columns": required_columns, "missing_columns": missing_columns},
        }
    )

    cp3_ok = cp1_ok and int(row_count) >= min_rows
    checkpoints.append(
        {
            "name": "CP3_返回行数满足阈值",
            "status": "PASS" if cp3_ok else "FAIL",
            "detail": {"row_count": row_count, "min_rows": min_rows},
        }
    )

    null_stats: dict[str, Any] = {}
    cp4_ok = cp1_ok
    if cp1_ok and row_count > 0:
        for key in key_columns:
            if key not in columns:
                null_stats[key] = "missing"
                cp4_ok = False
                continue
            empty_count = 0
            for row in records:
                value = row.get(key)
                if value is None or (isinstance(value, str) and not value.strip()):
                    empty_count += 1
            null_stats[key] = empty_count
            if empty_count > 0:
                cp4_ok = False
    checkpoints.append(
        {
            "name": "CP4_关键字段在非空结果中无空值",
            "status": "PASS" if cp4_ok else "FAIL",
            "detail": {"key_columns": key_columns, "null_or_empty_count": null_stats},
        }
    )
    return checkpoints


def format_cn_number(value: Any) -> str:
    try:
        number = float(value)
    except Exception:
        return str(value) if value is not None else "-"
    if abs(number) >= 100000000:
        return f"{number / 100000000:.2f}亿元"
    if abs(number) >= 10000:
        return f"{number / 10000:.2f}万元"
    return f"{number:.2f}"


def summarize_market(company: dict[str, Any], daily_rows: list[dict[str, Any]], daily_basic_rows: list[dict[str, Any]]) -> str:
    if not daily_rows:
        return f"{company.get('name') or company.get('com_name') or company.get('ts_code')} 当前本地没有可用行情数据。"
    latest = daily_rows[0]
    parts = [
        f"{company.get('name') or company.get('com_name') or company.get('ts_code')}最新行情日期为{latest.get('trade_date', '-')}",
        f"收盘价{latest.get('close', '-')}",
        f"开盘价{latest.get('open', '-')}",
        f"最高价{latest.get('high', '-')}",
        f"最低价{latest.get('low', '-')}",
        f"成交量{latest.get('vol', '-')}",
    ]
    if daily_basic_rows:
        basic = daily_basic_rows[0]
        parts.append(f"市盈率PE{basic.get('pe', '-')}")
        parts.append(f"市净率PB{basic.get('pb', '-')}")
    return "；".join(parts) + "。"


def summarize_business(company: dict[str, Any], segments: list[dict[str, Any]]) -> str:
    company_name = company.get("name") or company.get("com_name") or company.get("ts_code")
    profile = []
    if company.get("industry"):
        profile.append(f"所属行业为{company.get('industry')}")
    if company.get("market"):
        profile.append(f"市场板块为{company.get('market')}")
    if company.get("main_business"):
        profile.append(f"主营业务为{company.get('main_business')}")
    top_segments = [row.get("bz_item") for row in segments[:3] if row.get("bz_item")]
    if top_segments:
        profile.append("最近主营构成包括" + "、".join(top_segments))
    if not profile:
        return f"{company_name} 当前本地只有基础标识信息，主营业务细项数据不足。"
    return f"{company_name}" + "；".join(profile) + "。"


def summarize_finance(company: dict[str, Any], income_rows: list[dict[str, Any]], indicator_rows: list[dict[str, Any]]) -> str:
    company_name = company.get("name") or company.get("com_name") or company.get("ts_code")
    if not income_rows and not indicator_rows:
        return f"{company_name} 当前本地没有可用财务数据。"
    latest_income = income_rows[0] if income_rows else {}
    latest_indicator = indicator_rows[0] if indicator_rows else {}
    parts = [f"{company_name}财务口径最新期为{latest_income.get('end_date') or latest_indicator.get('end_date') or '-'}"]
    if latest_income.get("revenue") is not None:
        parts.append(f"营业收入{format_cn_number(latest_income.get('revenue'))}")
    if latest_income.get("n_income_attr_p") is not None:
        parts.append(f"归母净利润{format_cn_number(latest_income.get('n_income_attr_p'))}")
    if latest_indicator.get("roe") is not None:
        parts.append(f"ROE{latest_indicator.get('roe')}")
    if latest_indicator.get("grossprofit_margin") is not None:
        parts.append(f"毛利率{latest_indicator.get('grossprofit_margin')}")
    return "；".join(parts) + "。"


def summarize_ownership(company: dict[str, Any], top10_rows: list[dict[str, Any]], pledge_rows: list[dict[str, Any]], holder_trade_rows: list[dict[str, Any]]) -> str:
    company_name = company.get("name") or company.get("com_name") or company.get("ts_code")
    parts = [company_name]
    if top10_rows:
        top_names = [row.get("holder_name") for row in top10_rows[:3] if row.get("holder_name")]
        if top_names:
            parts.append("前十大股东中靠前股东包括" + "、".join(top_names))
    if pledge_rows:
        latest_pledge = pledge_rows[0]
        if latest_pledge.get("pledge_count") is not None:
            parts.append(f"最新质押次数{latest_pledge.get('pledge_count')}")
    if holder_trade_rows:
        latest_trade = holder_trade_rows[0]
        if latest_trade.get("holder_name") and latest_trade.get("in_de"):
            parts.append(f"最近股东变动主体为{latest_trade.get('holder_name')}，方向为{latest_trade.get('in_de')}")
    if len(parts) == 1:
        return f"{company_name} 当前本地股权结构数据不足。"
    return "；".join(parts) + "。"


def has_sync_errors(sync_actions: list[dict[str, Any]]) -> bool:
    for item in sync_actions:
        if item.get("error") or item.get("status") == "missing_local_data":
            return True
    return False


def collect_missing_items(sync_actions: list[dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    for item in sync_actions:
        api_name = item.get("api_name") or item.get("scenario") or "unknown"
        if item.get("status") == "missing_local_data":
            period = item.get("period")
            if period:
                missing.append(f"{api_name}:{period}")
            else:
                missing.append(str(api_name))
        elif item.get("error"):
            period = item.get("period")
            if period:
                missing.append(f"{api_name}:{period}")
            else:
                missing.append(str(api_name))
    return missing


def build_market_report(
    company: dict[str, Any],
    daily_rows: list[dict[str, Any]],
    daily_basic_rows: list[dict[str, Any]],
    sync_actions: list[dict[str, Any]],
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    coverage = "完整" if not has_sync_errors(sync_actions) else "部分完整"
    latest = daily_rows[0] if daily_rows else {}
    findings: list[str] = []
    if latest:
        findings.append(f"最新交易日为 {latest.get('trade_date', '-')}")
        findings.append(f"最新收盘价为 {latest.get('close', '-')}")
        if daily_basic_rows:
            basic = daily_basic_rows[0]
            if basic.get("pe") not in (None, ""):
                findings.append(f"最新 PE 为 {basic.get('pe')}")
            if basic.get("pb") not in (None, ""):
                findings.append(f"最新 PB 为 {basic.get('pb')}")
    conclusion = (
        f"{company.get('name') or company.get('com_name') or company.get('ts_code')} 的行情数据已覆盖 {start_date} 至 {end_date}。"
        if daily_rows
        else f"{company.get('name') or company.get('com_name') or company.get('ts_code')} 当前没有可用行情数据。"
    )
    return {
        "title": "市场行情分析",
        "conclusion": conclusion,
        "key_findings": findings,
        "coverage": {
            "status": coverage,
            "window": {"start_date": start_date, "end_date": end_date},
            "missing_items": collect_missing_items(sync_actions),
        },
        "next_actions": [
            "如需最新行情，使用 refresh 模式重新拉取。",
            "如需估值或换手等补充指标，确保 daily_basic 已补齐。",
        ],
    }


def build_business_report(
    company: dict[str, Any],
    segments: list[dict[str, Any]],
    sync_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    findings: list[str] = []
    if company.get("industry"):
        findings.append(f"所属行业：{company.get('industry')}")
    if company.get("main_business"):
        findings.append(f"主营业务：{company.get('main_business')}")
    if segments:
        top_segments = [row.get("bz_item") for row in segments[:5] if row.get("bz_item")]
        if top_segments:
            findings.append("最近主营构成包括：" + "、".join(top_segments))
    conclusion = (
        f"{company.get('name') or company.get('com_name') or company.get('ts_code')} 已具备主营业务分析所需的基础资料。"
        if findings
        else f"{company.get('name') or company.get('com_name') or company.get('ts_code')} 的主营业务资料仍不足。"
    )
    return {
        "title": "主营业务分析",
        "conclusion": conclusion,
        "key_findings": findings,
        "coverage": {
            "status": "完整" if not has_sync_errors(sync_actions) else "部分完整",
            "missing_items": collect_missing_items(sync_actions),
        },
        "next_actions": [
            "如需更稳定的主营口径，建议补最近两个报告期的 fina_mainbz。",
            "如需结合年报文字说明，可后续叠加公告或年报数据源。",
        ],
    }


def build_finance_report(
    company: dict[str, Any],
    income_rows: list[dict[str, Any]],
    indicator_rows: list[dict[str, Any]],
    periods: list[str],
    sync_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    findings: list[str] = []
    latest_income = income_rows[0] if income_rows else {}
    latest_indicator = indicator_rows[0] if indicator_rows else {}
    if latest_income.get("revenue") is not None:
        findings.append(f"最新营业收入：{format_cn_number(latest_income.get('revenue'))}")
    if latest_income.get("n_income_attr_p") is not None:
        findings.append(f"最新归母净利润：{format_cn_number(latest_income.get('n_income_attr_p'))}")
    if latest_indicator.get("roe") not in (None, ""):
        findings.append(f"最新 ROE：{latest_indicator.get('roe')}")
    if latest_indicator.get("grossprofit_margin") not in (None, ""):
        findings.append(f"最新毛利率：{latest_indicator.get('grossprofit_margin')}")
    conclusion = (
        f"{company.get('name') or company.get('com_name') or company.get('ts_code')} 已覆盖近三年及最近一期的核心财务分析框架。"
        if income_rows or indicator_rows
        else f"{company.get('name') or company.get('com_name') or company.get('ts_code')} 当前缺少核心财务数据。"
    )
    return {
        "title": "财务情况分析",
        "conclusion": conclusion,
        "key_findings": findings,
        "coverage": {
            "status": "完整" if not has_sync_errors(sync_actions) else "部分完整",
            "target_periods": periods,
            "missing_items": collect_missing_items(sync_actions),
        },
        "next_actions": [
            "如需趋势判断，继续对收入、利润、ROE 做多期同比或复合增速分析。",
            "如需质量分析，补充资产负债表与现金流匹配关系解读。",
        ],
    }


def build_ownership_report(
    company: dict[str, Any],
    top10_rows: list[dict[str, Any]],
    pledge_rows: list[dict[str, Any]],
    holder_trade_rows: list[dict[str, Any]],
    sync_actions: list[dict[str, Any]],
    target_period: str,
) -> dict[str, Any]:
    findings: list[str] = []
    if top10_rows:
        top_names = [row.get("holder_name") for row in top10_rows[:3] if row.get("holder_name")]
        if top_names:
            findings.append("前十大股东核心主体：" + "、".join(top_names))
    if pledge_rows:
        latest_pledge = pledge_rows[0]
        if latest_pledge.get("pledge_count") not in (None, ""):
            findings.append(f"最新质押次数：{latest_pledge.get('pledge_count')}")
    if holder_trade_rows:
        latest_trade = holder_trade_rows[0]
        if latest_trade.get("holder_name") and latest_trade.get("in_de"):
            findings.append(f"最近增减持主体：{latest_trade.get('holder_name')}，方向：{latest_trade.get('in_de')}")
    conclusion = (
        f"{company.get('name') or company.get('com_name') or company.get('ts_code')} 已具备股权结构分析的基础数据。"
        if findings
        else f"{company.get('name') or company.get('com_name') or company.get('ts_code')} 当前股权结构数据不足。"
    )
    return {
        "title": "股权结构分析",
        "conclusion": conclusion,
        "key_findings": findings,
        "coverage": {
            "status": "完整" if not has_sync_errors(sync_actions) else "部分完整",
            "target_period": target_period,
            "missing_items": collect_missing_items(sync_actions),
        },
        "next_actions": [
            "如需判断集中度变化，建议补多个 period 的 top10_holders。",
            "如需观察短期行为变化，建议结合更多 ann_date 的股东增减持数据。",
        ],
    }


def report_to_analysis_text(report: dict[str, Any]) -> str:
    title = report.get("title", "分析报告")
    conclusion = report.get("conclusion", "")
    findings = report.get("key_findings", [])
    coverage = report.get("coverage", {})
    next_actions = report.get("next_actions", [])

    lines = [f"{title}：{conclusion}"]
    if findings:
        lines.append("关键发现：")
        for item in findings:
            lines.append(f"- {item}")
    status = coverage.get("status")
    if status:
        missing = coverage.get("missing_items", [])
        if missing:
            lines.append(f"数据覆盖：当前为{status}，仍缺少 {', '.join(missing)}。")
        else:
            lines.append(f"数据覆盖：当前为{status}。")
    if next_actions:
        lines.append("后续建议：")
        for item in next_actions:
            lines.append(f"- {item}")
    return "\n".join(lines)


def run_case(args: argparse.Namespace, runtime: dict[str, Any], cases: list[dict[str, Any]]) -> int:
    try:
        case_cfg = resolve_case(args.case, cases)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "invalid_input", "message": str(exc)}, ensure_ascii=False, indent=2))
        return 2

    error = None
    http_status = None
    response_data: dict[str, Any] = {"api_name": case_cfg["api_name"]}
    raw_body: dict[str, Any] | None = None

    try:
        query_result = execute_query(
            api_name=case_cfg["api_name"],
            params=case_cfg.get("params", {}),
            fields=case_cfg.get("fields", ""),
            runtime=runtime,
            cache_db=Path(args.cache_db).resolve(),
            warehouse_db=Path(args.warehouse_db).resolve(),
            refresh=args.refresh,
            cache_only=args.cache_only,
        )
        http_status = query_result["http_status"]
        raw_body = query_result["body"]
        response_data = {
            "api_name": case_cfg["api_name"],
            "columns": query_result["columns"],
            "row_count": len(query_result["raw_records"]),
            "records": query_result["records"],
            "raw_records": query_result["raw_records"],
            "bonus_points_balance": raw_body.get("bonus_points_balance"),
            "recent_deducted_points": raw_body.get("recent_deducted_points"),
            "trade_order_id": raw_body.get("trade_order_id"),
            "cache": query_result["cache"],
            "warehouse": query_result["warehouse"],
        }
    except Exception as exc:
        error = str(exc)
        response_data = {"api_name": case_cfg["api_name"], "error": error}

    checkpoints = build_checkpoints(case_cfg, response_data, error, http_status)
    step_status = "PASS" if all(item["status"] == "PASS" for item in checkpoints) else "FAIL"
    result = {
        "tc_id": case_cfg["tc_id"],
        "scope": case_cfg.get("scope", "api"),
        "short_name": case_cfg["short_name"],
        "timezone": "Asia/Shanghai",
        "start_time": now_text(),
        "request_data": {
            "api_name": case_cfg["api_name"],
            "params": case_cfg.get("params", {}),
            "fields": case_cfg.get("fields", ""),
            "required_columns": case_cfg.get("required_columns", []),
            "key_columns": case_cfg.get("key_columns", []),
            "min_rows": case_cfg.get("min_rows", 0),
        },
        "steps": [
            {
                "step": "call_servicehub_tushare_api",
                "status": step_status,
                "checkpoints": checkpoints,
                "details": {
                    "response_data": response_data,
                    "raw_response": raw_body,
                },
            }
        ],
    }

    out_dir = Path(args.output_dir).resolve() if args.output_dir else RESULT_DIR
    out_name = f"tc_{case_cfg['tc_id']}_api_{case_cfg['short_name']}_{now_file_ts()}.json"
    out_path = out_dir / out_name
    save_json(out_path, result)
    print(json.dumps({"ok": step_status == "PASS", "case": case_cfg["short_name"], "result_file": str(out_path), "result": result}, ensure_ascii=False, indent=2))
    return 0 if step_status == "PASS" else 1


def run_custom_query(args: argparse.Namespace, runtime: dict[str, Any]) -> int:
    try:
        params = json.loads(args.params) if args.params else {}
        if not isinstance(params, dict):
            raise ValueError("params 必须是 JSON 对象。")
        if not args.api_name.strip():
            raise ValueError("api_name 不能为空。")
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "invalid_input", "message": str(exc)}, ensure_ascii=False, indent=2))
        return 2

    try:
        query_result = execute_query(
            api_name=args.api_name.strip(),
            params=params,
            fields=args.fields or "",
            runtime=runtime,
            cache_db=Path(args.cache_db).resolve(),
            warehouse_db=Path(args.warehouse_db).resolve(),
            refresh=args.refresh,
            cache_only=args.cache_only,
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "request_failed", "message": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    body = query_result["body"]
    http_status = query_result["http_status"]
    result = {
        "ok": http_status == 200 and body.get("code") == 200,
        "http_status": http_status,
        "request_data": {"api_name": args.api_name.strip(), "params": params, "fields": args.fields or ""},
        "cache": query_result["cache"],
        "warehouse": query_result["warehouse"],
        "response": body,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def scenario_query(args: argparse.Namespace, runtime: dict[str, Any]) -> int:
    cache_db = Path(args.cache_db).resolve()
    warehouse_db = Path(args.warehouse_db).resolve()
    company, resolve_log = resolve_company_with_autofill(
        args.identifier,
        runtime,
        cache_db,
        warehouse_db,
        refresh=args.refresh,
        cache_only=args.cache_only,
    )
    if not company:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "company_not_found",
                    "message": f"无法解析标的：{args.identifier}",
                    "resolve_log": resolve_log,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    ts_code = company["ts_code"]
    sync_actions: list[dict[str, Any]] = []
    scenario = args.scenario

    if scenario == "market":
        end_date = args.end_date or today_ymd()
        start_date = args.start_date or (datetime.now(TZ) - timedelta(days=args.days)).strftime("%Y%m%d")
        need_sync = args.refresh or not warehouse_has_market_window(warehouse_db, ts_code, start_date, end_date)
        if args.cache_only and need_sync:
            sync_actions.append({"status": "missing_local_data", "scenario": scenario, "start_date": start_date, "end_date": end_date})
        elif need_sync:
            for api_name, fields in [
                ("daily", "ts_code,trade_date,open,high,low,close,vol,amount"),
                ("daily_basic", "ts_code,trade_date,close,turnover_rate,pe,pb,total_mv,circ_mv"),
            ]:
                try:
                    result = execute_query(
                        api_name=api_name,
                        params={"ts_code": ts_code, "start_date": start_date, "end_date": end_date},
                        fields=fields,
                        runtime=runtime,
                        cache_db=cache_db,
                        warehouse_db=warehouse_db,
                        refresh=args.refresh,
                        cache_only=args.cache_only,
                    )
                    sync_actions.append(
                        {
                            "api_name": api_name,
                            "row_count": len(result["records"]),
                            "cache": result["cache"],
                            "warehouse": result["warehouse"],
                        }
                    )
                except Exception as exc:
                    sync_actions.append({"api_name": api_name, "error": str(exc)})
        market_daily = fetch_warehouse_rows(warehouse_db, "market_daily", ts_code, "trade_date", args.limit)
        market_daily_basic = fetch_warehouse_rows(warehouse_db, "market_daily_basic", ts_code, "trade_date", args.limit)
        report = build_market_report(company, market_daily, market_daily_basic, sync_actions, start_date, end_date)
        payload = {
            "ok": True,
            "scenario": scenario,
            "identifier": args.identifier,
            "resolved_company": company,
            "resolve_log": resolve_log,
            "sync_actions": sync_actions,
            "summary": summarize_market(company, market_daily, market_daily_basic),
            "report": report,
            "analysis_text": report_to_analysis_text(report),
            "market_daily": market_daily,
            "market_daily_basic": market_daily_basic,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if scenario == "business":
        required_calls = [
            ("stock_basic", "stock_basic_records", {"ts_code": ts_code, "list_status": "L"}, ""),
            ("stock_company", "stock_company_records", {"ts_code": ts_code}, ""),
            ("fina_mainbz", "business_segments", {"ts_code": ts_code, "period": args.latest_period or latest_quarter_end(), "type": "P"}, ""),
        ]
        for api_name, table_name, params, fields in required_calls:
            if api_name == "fina_mainbz":
                need_sync = args.refresh or not warehouse_has_exact_rows(
                    warehouse_db,
                    table_name,
                    ts_code,
                    {"end_date": params["period"], "type": params["type"]},
                )
            else:
                need_sync = args.refresh or warehouse_row_count(warehouse_db, table_name, ts_code) == 0
            if args.cache_only and need_sync:
                sync_actions.append({"api_name": api_name, "status": "missing_local_data"})
                continue
            if not need_sync:
                continue
            try:
                result = execute_query(
                    api_name=api_name,
                    params=params,
                    fields=fields,
                    runtime=runtime,
                    cache_db=cache_db,
                    warehouse_db=warehouse_db,
                    refresh=args.refresh,
                    cache_only=args.cache_only,
                )
                sync_actions.append(
                    {
                        "api_name": api_name,
                        "row_count": len(result["records"]),
                        "cache": result["cache"],
                        "warehouse": result["warehouse"],
                    }
                )
            except Exception as exc:
                sync_actions.append({"api_name": api_name, "error": str(exc)})
        business_segments = fetch_warehouse_rows(warehouse_db, "business_segments", ts_code, "end_date", args.limit)
        report = build_business_report(resolve_company_identifier(warehouse_db, ts_code) or company, business_segments, sync_actions)
        payload = {
            "ok": True,
            "scenario": scenario,
            "identifier": args.identifier,
            "resolved_company": resolve_company_identifier(warehouse_db, ts_code) or company,
            "resolve_log": resolve_log,
            "sync_actions": sync_actions,
            "summary": summarize_business(resolve_company_identifier(warehouse_db, ts_code) or company, business_segments),
            "report": report,
            "analysis_text": report_to_analysis_text(report),
            "business_segments": business_segments,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if scenario == "finance":
        periods = finance_periods(args.years)
        for api_name, table_name in [
            ("income", "financial_income"),
            ("balancesheet", "financial_balancesheet"),
            ("cashflow", "financial_cashflow"),
            ("fina_indicator", "financial_indicator"),
        ]:
            missing = args.refresh or not warehouse_has_period_rows(warehouse_db, table_name, ts_code, "end_date", periods)
            if missing:
                for period in periods:
                    if args.cache_only:
                        sync_actions.append({"api_name": api_name, "period": period, "status": "missing_local_data"})
                        continue
                    try:
                        result = execute_query(
                            api_name=api_name,
                            params={"ts_code": ts_code, "period": period},
                            fields="",
                            runtime=runtime,
                            cache_db=cache_db,
                            warehouse_db=warehouse_db,
                            refresh=args.refresh,
                            cache_only=args.cache_only,
                        )
                        sync_actions.append(
                            {
                                "api_name": api_name,
                                "period": period,
                                "row_count": len(result["records"]),
                                "cache": result["cache"],
                                "warehouse": result["warehouse"],
                            }
                        )
                    except Exception as exc:
                        sync_actions.append({"api_name": api_name, "period": period, "error": str(exc)})
        income_rows = fetch_warehouse_rows(warehouse_db, "financial_income", ts_code, "end_date", args.limit)
        balancesheet_rows = fetch_warehouse_rows(warehouse_db, "financial_balancesheet", ts_code, "end_date", args.limit)
        cashflow_rows = fetch_warehouse_rows(warehouse_db, "financial_cashflow", ts_code, "end_date", args.limit)
        indicator_rows = fetch_warehouse_rows(warehouse_db, "financial_indicator", ts_code, "end_date", args.limit)
        report = build_finance_report(company, income_rows, indicator_rows, periods, sync_actions)
        payload = {
            "ok": True,
            "scenario": scenario,
            "identifier": args.identifier,
            "resolved_company": company,
            "resolve_log": resolve_log,
            "target_periods": periods,
            "sync_actions": sync_actions,
            "summary": summarize_finance(company, income_rows, indicator_rows),
            "report": report,
            "analysis_text": report_to_analysis_text(report),
            "income": income_rows,
            "balancesheet": balancesheet_rows,
            "cashflow": cashflow_rows,
            "fina_indicator": indicator_rows,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    target_period = args.latest_period or annual_periods(1)[0]
    ownership_calls = [
        ("top10_holders", "ownership_top10_holders", {"ts_code": ts_code, "period": target_period}, ""),
        ("top10_floatholders", "ownership_top10_floatholders", {"ts_code": ts_code, "period": target_period}, ""),
        ("pledge_stat", "ownership_pledge_stat", {"ts_code": ts_code}, ""),
        ("pledge_detail", "ownership_pledge_detail", {"ts_code": ts_code}, ""),
        ("stk_holdertrade", "ownership_holder_trade", {"ts_code": ts_code, "ann_date": args.ann_date or target_period}, ""),
    ]
    for api_name, table_name, params, fields in ownership_calls:
        if api_name in {"top10_holders", "top10_floatholders"}:
            need_sync = args.refresh or not warehouse_has_exact_rows(
                warehouse_db,
                table_name,
                ts_code,
                {"end_date": target_period},
            )
        elif api_name == "stk_holdertrade":
            need_sync = args.refresh or not warehouse_has_exact_rows(
                warehouse_db,
                table_name,
                ts_code,
                {"ann_date": params["ann_date"]},
            )
        else:
            need_sync = args.refresh or warehouse_row_count(warehouse_db, table_name, ts_code) == 0
        if args.cache_only and need_sync:
            sync_actions.append({"api_name": api_name, "status": "missing_local_data"})
            continue
        if not need_sync:
            continue
        try:
            result = execute_query(
                api_name=api_name,
                params=params,
                fields=fields,
                runtime=runtime,
                cache_db=cache_db,
                warehouse_db=warehouse_db,
                refresh=args.refresh,
                cache_only=args.cache_only,
            )
            sync_actions.append(
                {
                    "api_name": api_name,
                    "row_count": len(result["records"]),
                    "cache": result["cache"],
                    "warehouse": result["warehouse"],
                }
            )
        except Exception as exc:
            sync_actions.append({"api_name": api_name, "error": str(exc)})
    top10_rows = fetch_warehouse_rows(warehouse_db, "ownership_top10_holders", ts_code, "end_date", args.limit)
    top10_float_rows = fetch_warehouse_rows(warehouse_db, "ownership_top10_floatholders", ts_code, "end_date", args.limit)
    pledge_stat_rows = fetch_warehouse_rows(warehouse_db, "ownership_pledge_stat", ts_code, "end_date", args.limit)
    pledge_detail_rows = fetch_warehouse_rows(warehouse_db, "ownership_pledge_detail", ts_code, "ann_date", args.limit)
    holder_trade_rows = fetch_warehouse_rows(warehouse_db, "ownership_holder_trade", ts_code, "ann_date", args.limit)
    report = build_ownership_report(company, top10_rows, pledge_stat_rows, holder_trade_rows, sync_actions, target_period)
    payload = {
        "ok": True,
        "scenario": scenario,
        "identifier": args.identifier,
        "resolved_company": company,
        "resolve_log": resolve_log,
        "sync_actions": sync_actions,
        "summary": summarize_ownership(company, top10_rows, pledge_stat_rows, holder_trade_rows),
        "report": report,
        "analysis_text": report_to_analysis_text(report),
        "top10_holders": top10_rows,
        "top10_floatholders": top10_float_rows,
        "pledge_stat": pledge_stat_rows,
        "pledge_detail": pledge_detail_rows,
        "holder_trade": holder_trade_rows,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def list_cases(cases: list[dict[str, Any]]) -> int:
    payload = [
        {
            "tc_id": item["tc_id"],
            "api_name": item["api_name"],
            "title_cn": item["title_cn"],
            "required_columns": item["required_columns"],
            "params": item["params"],
        }
        for item in cases
    ]
    print(json.dumps({"ok": True, "cases": payload}, ensure_ascii=False, indent=2))
    return 0


def warehouse_query(args: argparse.Namespace) -> int:
    db_path = Path(args.warehouse_db).resolve()
    company = enrich_company_profile(db_path, resolve_company_identifier(db_path, args.identifier))
    if not company:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "company_not_found",
                    "message": f"本地业务库中未找到标的：{args.identifier}",
                    "warehouse_db": str(db_path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    ts_code = company["ts_code"]
    limit = args.limit
    payload: dict[str, Any] = {
        "ok": True,
        "scenario": args.scenario,
        "identifier": args.identifier,
        "resolved_company": company,
        "warehouse_db": str(db_path),
    }

    if args.scenario == "company":
        payload["company_profile"] = company
        payload["summary"] = summarize_business(company, [])
        report = build_business_report(company, [], [])
        payload["report"] = report
        payload["analysis_text"] = report_to_analysis_text(report)
    elif args.scenario == "market":
        market_daily = fetch_warehouse_rows(db_path, "market_daily", ts_code, "trade_date", limit)
        market_daily_basic = fetch_warehouse_rows(db_path, "market_daily_basic", ts_code, "trade_date", limit)
        start_date, end_date = infer_market_window(market_daily, market_daily_basic)
        payload["summary"] = summarize_market(company, market_daily, market_daily_basic)
        report = build_market_report(company, market_daily, market_daily_basic, [], start_date, end_date)
        payload["report"] = report
        payload["analysis_text"] = report_to_analysis_text(report)
        payload["market_daily"] = market_daily
        payload["market_daily_basic"] = market_daily_basic
    elif args.scenario == "business":
        business_segments = fetch_warehouse_rows(db_path, "business_segments", ts_code, "end_date", limit)
        payload["company_profile"] = company
        payload["summary"] = summarize_business(company, business_segments)
        report = build_business_report(company, business_segments, [])
        payload["report"] = report
        payload["analysis_text"] = report_to_analysis_text(report)
        payload["business_segments"] = business_segments
    elif args.scenario == "finance":
        income_rows = fetch_warehouse_rows(db_path, "financial_income", ts_code, "end_date", limit)
        balancesheet_rows = fetch_warehouse_rows(db_path, "financial_balancesheet", ts_code, "end_date", limit)
        cashflow_rows = fetch_warehouse_rows(db_path, "financial_cashflow", ts_code, "end_date", limit)
        indicator_rows = fetch_warehouse_rows(db_path, "financial_indicator", ts_code, "end_date", limit)
        payload["summary"] = summarize_finance(company, income_rows, indicator_rows)
        report = build_finance_report(company, income_rows, indicator_rows, [], [])
        payload["report"] = report
        payload["analysis_text"] = report_to_analysis_text(report)
        payload["income"] = income_rows
        payload["balancesheet"] = balancesheet_rows
        payload["cashflow"] = cashflow_rows
        payload["fina_indicator"] = indicator_rows
    elif args.scenario == "ownership":
        top10_rows = fetch_warehouse_rows(db_path, "ownership_top10_holders", ts_code, "end_date", limit)
        top10_float_rows = fetch_warehouse_rows(db_path, "ownership_top10_floatholders", ts_code, "end_date", limit)
        pledge_stat_rows = fetch_warehouse_rows(db_path, "ownership_pledge_stat", ts_code, "end_date", limit)
        pledge_detail_rows = fetch_warehouse_rows(db_path, "ownership_pledge_detail", ts_code, "ann_date", limit)
        holder_trade_rows = fetch_warehouse_rows(db_path, "ownership_holder_trade", ts_code, "ann_date", limit)
        payload["summary"] = summarize_ownership(company, top10_rows, pledge_stat_rows, holder_trade_rows)
        report = build_ownership_report(company, top10_rows, pledge_stat_rows, holder_trade_rows, [], "-")
        payload["report"] = report
        payload["analysis_text"] = report_to_analysis_text(report)
        payload["top10_holders"] = top10_rows
        payload["top10_floatholders"] = top10_float_rows
        payload["pledge_stat"] = pledge_stat_rows
        payload["pledge_detail"] = pledge_detail_rows
        payload["holder_trade"] = holder_trade_rows

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TuShare ServiceHub 助手命令行工具")
    parser.add_argument("--username", default="", help="ServiceHub 用户名")
    parser.add_argument("--passtoken", default="", help="ServiceHub 密码或 passtoken")
    parser.add_argument("--base-url", default="", help="ServiceHub 服务地址")
    parser.add_argument("--credentials-file", default=str(DEFAULT_CREDENTIALS_PATH), help="本地凭证文件路径")
    parser.add_argument("--cache-db", default=str(CACHE_DB_PATH), help="本地缓存数据库路径")
    parser.add_argument("--warehouse-db", default=str(WAREHOUSE_DB_PATH), help="本地业务数据库路径")
    parser.add_argument("--refresh", action="store_true", help="忽略本地缓存，强制走 ServiceHub")
    parser.add_argument("--cache-only", action="store_true", help="只读取本地缓存，不发起远程请求")
    parser.add_argument("--save-credentials", action="store_true", help="将当前传入凭证写回本地凭证文件")

    subparsers = parser.add_subparsers(dest="command", required=True, help="子命令")

    subparsers.add_parser("list-cases", help="列出内置标准用例")

    p_run_case = subparsers.add_parser("run-case", help="执行单个内置标准用例")
    p_run_case.add_argument("--case", required=True, help="用例名，支持 short_name 或中文标题")
    p_run_case.add_argument("--output-dir", default="", help="结果输出目录")

    p_custom = subparsers.add_parser("custom-query", help="执行自定义 TuShare 查询")
    p_custom.add_argument("--api-name", required=True, help="TuShare api_name")
    p_custom.add_argument("--params", required=True, help="JSON 字符串形式的参数对象")
    p_custom.add_argument("--fields", default="", help="逗号分隔字段列表")

    p_scenario = subparsers.add_parser("scenario-query", help="按业务场景自动补数并输出本地结果")
    p_scenario.add_argument("--scenario", required=True, choices=["market", "business", "finance", "ownership"], help="业务场景")
    p_scenario.add_argument("--identifier", required=True, help="股票代码、股票简称或公司名")
    p_scenario.add_argument("--start-date", default="", help="行情场景开始日期 YYYYMMDD")
    p_scenario.add_argument("--end-date", default="", help="行情场景结束日期 YYYYMMDD")
    p_scenario.add_argument("--days", type=int, default=90, help="行情场景默认回看天数")
    p_scenario.add_argument("--years", type=int, default=3, help="财务场景默认回看完整年度数")
    p_scenario.add_argument("--latest-period", default="", help="业务或股权场景指定 period")
    p_scenario.add_argument("--ann-date", default="", help="股东增减持场景指定公告日期 YYYYMMDD")
    p_scenario.add_argument("--limit", type=int, default=20, help="每类结果返回的最大记录数")

    p_warehouse = subparsers.add_parser("warehouse-query", help="按业务场景读取本地业务数据库")
    p_warehouse.add_argument("--scenario", required=True, choices=["company", "market", "business", "finance", "ownership"], help="业务场景")
    p_warehouse.add_argument("--identifier", required=True, help="股票代码、股票简称或公司名")
    p_warehouse.add_argument("--limit", type=int, default=20, help="每类结果返回的最大记录数")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    credentials_path = Path(args.credentials_file).resolve()
    runtime = resolve_runtime_config(args, credentials_path)
    cases = load_case_map()

    if args.command == "list-cases":
        return list_cases(cases)
    if args.command == "run-case":
        return run_case(args, runtime, cases)
    if args.command == "scenario-query":
        return scenario_query(args, runtime)
    if args.command == "warehouse-query":
        return warehouse_query(args)
    return run_custom_query(args, runtime)


if __name__ == "__main__":
    sys.exit(main())
