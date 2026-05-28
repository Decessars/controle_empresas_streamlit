# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import app  # noqa: E402


TABLES = ["empresas", "settings", "demandas", "faturamento_mei"]


def sqlite_tables(source: Path) -> set[str]:
    with sqlite3.connect(source) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row[0] for row in rows}


def sql_type_for(series: pd.Series) -> str:
    if pd.api.types.is_integer_dtype(series):
        return "INTEGER"
    if pd.api.types.is_float_dtype(series):
        return "REAL"
    return "TEXT"


def ensure_target_columns(table: str, df: pd.DataFrame) -> None:
    existing = app.query_df(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_schema='public'
           AND table_name=?
        """,
        (table,),
    )
    existing_cols = set(existing["column_name"].tolist())
    for column in df.columns:
        if column not in existing_cols:
            app.ensure_column(table, column, sql_type_for(df[column]))


def reset_sequences() -> None:
    for table in ["empresas", "demandas", "faturamento_mei"]:
        app.execute(
            f"""
            SELECT setval(
                pg_get_serial_sequence('{table}', 'id'),
                COALESCE((SELECT MAX(id) FROM {table}), 1),
                true
            )
            """
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Migra cnpjs.db local para PostgreSQL online.")
    parser.add_argument(
        "--source",
        default=str(PROJECT_DIR.parent / "_dados_app" / "cnpjs.db"),
        help="Caminho do cnpjs.db local.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Apaga dados atuais do PostgreSQL antes de importar.",
    )
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()
    if not source.exists():
        raise SystemExit(f"Banco SQLite não encontrado: {source}")
    if not app.database_url():
        raise SystemExit("Defina DATABASE_URL ou .streamlit/secrets.toml antes de rodar a migração.")

    app.init_db()
    engine = app.get_engine()

    if args.replace:
        app.execute("TRUNCATE TABLE faturamento_mei, demandas, settings, empresas RESTART IDENTITY CASCADE")

    available = sqlite_tables(source)
    with sqlite3.connect(source) as sqlite_conn:
        for table in TABLES:
            if table not in available:
                print(f"Ignorado: tabela {table} não existe no SQLite.")
                continue
            df = pd.read_sql_query(f"SELECT * FROM {table}", sqlite_conn)
            if df.empty:
                print(f"Ignorado: tabela {table} está vazia.")
                continue
            ensure_target_columns(table, df)
            df.to_sql(table, engine, if_exists="append", index=False, method="multi")
            print(f"Importado: {table} ({len(df)} linhas).")

    reset_sequences()
    print("Migração concluída.")


if __name__ == "__main__":
    main()
