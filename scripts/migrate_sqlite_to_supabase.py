# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import importlib.util
import sqlite3
import sys
from pathlib import Path

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_DIR / "Exelencia Contabilidade.py"
DEFAULT_SQLITE_PATH = PROJECT_DIR / "data" / "cnpjs.db"


def load_app_module():
    spec = importlib.util.spec_from_file_location("controle_empresas_app", APP_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Nao foi possivel carregar {APP_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sqlite_tables(source: Path) -> set[str]:
    with sqlite3.connect(source) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row[0] for row in rows}


def sqlite_dataframe(source: Path, table: str) -> pd.DataFrame:
    with sqlite3.connect(source) as conn:
        return pd.read_sql_query(f"SELECT * FROM {table}", conn)


def target_columns(app, table: str) -> set[str]:
    df = app.query_df(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_schema='public'
           AND table_name=?
        """,
        (table,),
    )
    return set(df["column_name"].astype(str).tolist()) if not df.empty else set()


def normalize_value(value):
    if pd.isna(value):
        return None
    return value


def insert_row(app, table: str, row: dict, *, conflict_clause: str = "") -> int:
    data = {key: normalize_value(value) for key, value in row.items()}
    columns = list(data.keys())
    placeholders = ", ".join(["?"] * len(columns))
    column_sql = ", ".join(columns)
    sql = f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders}) {conflict_clause}".strip()
    return app.execute(sql, tuple(data[col] for col in columns))


def migrate_empresas(app, source: Path, available: set[str]) -> tuple[dict[int, int], int, int, int]:
    if "empresas" not in available:
        return {}, 0, 0, 0
    df = sqlite_dataframe(source, "empresas")
    if df.empty:
        return {}, 0, 0, 0

    cols = target_columns(app, "empresas")
    empresa_id_map: dict[int, int] = {}
    inserted = ignored = errors = 0

    for _, record in df.iterrows():
        row = record.to_dict()
        source_id = int(row.get("id") or 0)
        cnpj = str(row.get("cnpj") or "").strip()
        if not cnpj:
            errors += 1
            continue

        existing = app.empresa_row_by_cnpj(cnpj)
        if existing:
            ignored += 1
            empresa_id_map[source_id] = int(existing["id"])
            continue

        clean = {key: value for key, value in row.items() if key in cols and key != "id"}
        try:
            insert_row(app, "empresas", clean, conflict_clause="ON CONFLICT(cnpj) DO NOTHING")
            created = app.empresa_row_by_cnpj(cnpj)
            if created:
                inserted += 1
                empresa_id_map[source_id] = int(created["id"])
        except Exception as exc:
            errors += 1
            print(f"Erro empresa {cnpj}: {exc}")

    return empresa_id_map, inserted, ignored, errors


def migrate_child_table(
    app,
    source: Path,
    available: set[str],
    table: str,
    empresa_id_map: dict[int, int],
    conflict_clause: str,
) -> tuple[int, int]:
    if table not in available:
        return 0, 0
    df = sqlite_dataframe(source, table)
    if df.empty:
        return 0, 0

    cols = target_columns(app, table)
    inserted = errors = 0
    for _, record in df.iterrows():
        row = record.to_dict()
        source_empresa_id = int(row.get("empresa_id") or 0)
        target_empresa_id = empresa_id_map.get(source_empresa_id)
        if not target_empresa_id:
            errors += 1
            continue
        row["empresa_id"] = target_empresa_id
        clean = {key: value for key, value in row.items() if key in cols and key != "id"}
        try:
            inserted += insert_row(app, table, clean, conflict_clause=conflict_clause)
        except Exception as exc:
            errors += 1
            print(f"Erro {table} empresa_id={source_empresa_id}: {exc}")
    return inserted, errors


def migrate_settings(app, source: Path, available: set[str]) -> tuple[int, int]:
    if "settings" not in available:
        return 0, 0
    df = sqlite_dataframe(source, "settings")
    inserted = errors = 0
    for _, record in df.iterrows():
        row = record.to_dict()
        try:
            inserted += insert_row(
                app,
                "settings",
                {"key": row.get("key"), "value": row.get("value")},
                conflict_clause="ON CONFLICT(key) DO NOTHING",
            )
        except Exception as exc:
            errors += 1
            print(f"Erro settings key={row.get('key')}: {exc}")
    return inserted, errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Migra dados do SQLite local para Supabase PostgreSQL.")
    parser.add_argument("--source", default=str(DEFAULT_SQLITE_PATH), help="Caminho do SQLite local.")
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()
    if not source.exists():
        raise SystemExit(f"SQLite nao encontrado: {source}")

    app = load_app_module()
    if not app.get_database_url():
        raise SystemExit("Defina DATABASE_URL no ambiente ou nos Secrets antes de migrar.")
    if not app.using_postgres():
        raise SystemExit("DATABASE_URL informado nao parece ser PostgreSQL.")

    app.init_db()
    if not app.test_database_connection():
        raise SystemExit("Falha no teste de conexao com o banco de destino.")

    available = sqlite_tables(source)
    empresa_id_map, empresas_inserted, empresas_ignored, empresa_errors = migrate_empresas(app, source, available)
    demandas_inserted, demandas_errors = migrate_child_table(
        app,
        source,
        available,
        "demandas",
        empresa_id_map,
        "ON CONFLICT(empresa_id, competencia, tipo) DO NOTHING",
    )
    faturamento_inserted, faturamento_errors = migrate_child_table(
        app,
        source,
        available,
        "faturamento_mei",
        empresa_id_map,
        "ON CONFLICT(empresa_id, competencia) DO NOTHING",
    )
    settings_inserted, settings_errors = migrate_settings(app, source, available)

    print("Migracao concluida.")
    print(f"Empresas inseridas: {empresas_inserted}")
    print(f"Empresas ignoradas por duplicidade: {empresas_ignored}")
    print(f"Demandas migradas: {demandas_inserted}")
    print(f"Faturamento MEI migrado: {faturamento_inserted}")
    print(f"Settings migrados: {settings_inserted}")
    print(f"Erros: {empresa_errors + demandas_errors + faturamento_errors + settings_errors}")


if __name__ == "__main__":
    main()
