# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import json
import os
import base64
import hashlib
import hmac
import secrets
import shutil
import sqlite3
import uuid
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import tomllib

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from sqlalchemy import create_engine, text

try:
    import extra_streamlit_components as esc
except Exception:  # pragma: no cover - optional dependency for cookie persistence
    esc = None


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DEFAULT_DB_PATH = DATA_DIR / "cnpjs.db"
DB_PATH = Path(os.getenv("CONTROLE_EMPRESAS_DB", str(DEFAULT_DB_PATH))).expanduser()
AUTH_EXPORT_PATH = APP_DIR / "usuarios_senhas.txt"
LOGO_PATH = APP_DIR / "logo.png"
AUTH_SESSION_TTL_SECONDS = 3600
AUTH_COOKIE_NAME = "ce_auth_token"
AUTH_SESSION_DEFAULT_PAGE = "Modulos"
AUTH_SESSION_DEFAULT_LABEL = "📂 Módulos"
SCHEMA_VERSION = "2026-05-31-01"
_ENGINE = None
_ENGINE_URL = None

USER_ROLES = {
    "admin_geral": "Administrador Geral",
    "contador": "Contador",
    "estagiario": "Estagiário",
    "usuario": "Usuário",
}

SPECIAL_USER_ROLES = {
    "DMLIMA": "admin_geral",
    "RAFAEL": "contador",
}

USER_MANAGEMENT_ALLOWED = {"DMLIMA", "RAFAEL"}
PASSWORD_MIN_LENGTH = 6
PBKDF2_ITERATIONS = 200_000

DEMAND_TYPES = [
    ("EXEC_FOLHA", "Execucao da Folha de Pagamento"),
    ("ENV_CONTRACHEQUES", "Envio de Contracheques"),
    ("GUIA_INSS", "Geracao/Envio Guia INSS"),
    ("GUIA_FGTS", "Geracao/Envio Guia FGTS"),
    ("GUIA_FGTS_PARC", "Parc FGTS"),
    ("PEDIR_INFOS", "Pedir Informacoes ao Cliente"),
    ("APUR_ISS", "Apuracao ISS"),
    ("APUR_SIMPLES", "Apuracao do Simples Nacional"),
    ("GUIA_MEI", "Gerar/Enviar DAS-MEI"),
    ("ENV_PARC_SIMPLES", "Enviar Parcelamento do Simples/MEI"),
    ("REL_MEI", "Relatorio Mensal do MEI"),
    ("GUIA_PREF", "Guia da Prefeitura"),
    ("REL_DEBITOS", "Relatorio de Debitos"),
    ("CONS_ICMS_ST", "Consulta ICMS-ST (SEFAZ)"),
    ("PUXAR_NF_SAIDA", "Puxar NF de Saida (SEFAZ)"),
    ("EMISSAO_NF", "Emissao NF"),
    ("COBRAR_HONORARIOS", "Cobrar Honorarios"),
    ("PARC_MENSAL", "Parcelamento Mensal (impostos)"),
    ("PARC_IMPOSTOS", "Parcelamento de Impostos (outro)"),
    ("DEFIS", "DEFIS"),
    ("OUTRA", "Outra Demanda"),
]

DEMAND_LABELS = dict(DEMAND_TYPES)
DEMAND_TYPE_ROWS = [
    {"codigo": idx, "nome_curto": code, "nome": label, "categoria": "operacional", "ordem": idx}
    for idx, (code, label) in enumerate(DEMAND_TYPES, start=1)
]
DEMANDA_STATUS = [
    "pendente",
    "em_andamento",
    "aguardando_cliente",
    "aguardando_documento",
    "concluida",
    "dispensada",
    "cancelada",
]
DEMANDA_STATUS_LABELS = {
    "pendente": "Pendente",
    "em_andamento": "Em andamento",
    "aguardando_cliente": "Aguardando cliente",
    "aguardando_documento": "Aguardando documento",
    "concluida": "Concluida",
    "dispensada": "Dispensada",
    "cancelada": "Cancelada",
}
DEMANDA_PRIORIDADES = ["baixa", "normal", "alta", "urgente"]
DEMANDA_DEPENDENCIAS_PADRAO = [
    ("ENV_CONTRACHEQUES", "EXEC_FOLHA"),
    ("GUIA_INSS", "EXEC_FOLHA"),
    ("GUIA_FGTS", "EXEC_FOLHA"),
    ("REL_MEI", "GUIA_MEI"),
]
REGIMES = ["Simples Nacional", "MEI", "Lucro Presumido", "Lucro Real", "Imune/Isenta", "Outro"]

MODULES = [
    {
        "title": "Cadastro de Empresas",
        "desc": "Lista compacta de empresas para consulta e referencia operacional.",
        "tag": "ATIVO",
        "icon": "E",
        "enabled": True,
        "page": "Empresas",
    },
    {
        "title": "Controle de Demandas",
        "desc": "Painel simples para consulta, filtro e marcacao das demandas.",
        "tag": "ATIVO",
        "icon": "D",
        "enabled": True,
        "page": "Demandas",
    },
]

NAV_MENU = {
    "📂 Módulos": "Modulos",
    "📊 Painel": "Painel",
    "👤 Novo Cliente": "Novo Cliente",
    "🏢 Empresas": "Empresas",
    "📋 Demandas": "Demandas",
    "🤖 Automação": "Automacao",
    "💰 Faturamento": "Faturamento",
    "💾 Backup": "Backup",
}

BUTTON_LABELS = {
    "ativas": "✅ Ativas",
    "excluidas": "🗑️ Excluídas",
    "importar": "📥 Importar",
    "exportar": "📤 Exportar",
    "incluir_cnpj": "➕ Incluir por CNPJ",
    "cadastro_on": "🔎 Cadastro On",
    "salvar": "💾 Salvar",
    "cancelar": "❌ Cancelar",
    "editar": "✏️ Editar",
    "excluir": "🗑️ Excluir",
    "atualizar": "🔄 Atualizar",
    "buscar": "🔎 Buscar",
    "limpar": "🧹 Limpar",
    "voltar": "⬅️ Voltar",
    "usuarios": "👥 Usuários",
    "backup": "💾 Backup",
    "demandas": "📋 Demandas",
    "faturamento": "💰 Faturamento",
    "automacao": "🤖 Automação",
}


WEB_DATA_DIR = APP_DIR / "data_web"
WEB_DATA_SQLITE_PATH = WEB_DATA_DIR / "dmls_web.sqlite"
WEB_EMPRESAS_CSV_PATH = WEB_DATA_DIR / "empresas_web.csv"
WEB_DEMANDAS_CSV_PATH = WEB_DATA_DIR / "demandas_web.csv"
WEB_USUARIOS_CSV_PATH = WEB_DATA_DIR / "usuarios_web.csv"
WEB_MARCACOES_CSV_PATH = WEB_DATA_DIR / "marcacoes_web.csv"
WEB_ACTION_LOG_CSV_PATH = WEB_DATA_DIR / "web_action_log.csv"
WEB_DATA_SOURCE_MODES = {"sqlite_local", "excel_snapshot", "csv_snapshot", "supabase"}

NAV_MENU = {
    "Home": "Painel",
    "Empresas": "Empresas",
    "Demandas": "Demandas",
}


def get_data_source_mode() -> str:
    mode = str(os.getenv("CONTROLE_EMPRESAS_DATA_SOURCE_MODE", "") or "").strip().lower()
    if not mode:
        try:
            mode = str(st.secrets.get("CONTROLE_EMPRESAS_DATA_SOURCE_MODE", "") or "").strip().lower()
        except Exception:
            mode = ""
    if mode not in WEB_DATA_SOURCE_MODES:
        if (WEB_DATA_DIR / "empresas_web.csv").exists() or (WEB_DATA_DIR / "demandas_web.csv").exists():
            mode = "csv_snapshot"
        elif WEB_DATA_SQLITE_PATH.exists():
            mode = "sqlite_local"
        else:
            mode = "csv_snapshot"
    return mode


def is_web_simple_mode() -> bool:
    return get_data_source_mode() in {"sqlite_local", "excel_snapshot", "csv_snapshot"}


@st.cache_data(ttl=60)
def load_web_data() -> dict[str, pd.DataFrame]:
    mode = get_data_source_mode()
    empresas = pd.DataFrame()
    demandas = pd.DataFrame()
    usuarios = pd.DataFrame()
    metadata: dict = {}

    if mode == "sqlite_local" and WEB_DATA_SQLITE_PATH.exists():
        empresas = _load_web_sqlite_df("empresas_web")
        demandas = _load_web_sqlite_df("demandas_web")
        usuarios = _load_web_sqlite_df("usuarios_web")
    else:
        empresas = _load_web_csv_or_excel("empresas_web")
        demandas = _load_web_csv_or_excel("demandas_web")
        usuarios = _load_web_csv_or_excel("usuarios_web")

    meta_path = WEB_DATA_DIR / "metadata_web.json"
    if meta_path.exists():
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            metadata = {}

    return {
        "empresas": empresas,
        "demandas": demandas,
        "usuarios": usuarios,
        "metadata": metadata if isinstance(metadata, dict) else {},
    }


def _ensure_web_data_dir() -> Path:
    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return WEB_DATA_DIR


def _load_web_sqlite_df(table: str) -> pd.DataFrame:
    if not WEB_DATA_SQLITE_PATH.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(str(WEB_DATA_SQLITE_PATH)) as conn:
            return pd.read_sql_query(f"SELECT * FROM {table}", conn)
    except Exception:
        return pd.DataFrame()


def _load_web_csv_or_excel(stem: str) -> pd.DataFrame:
    _ensure_web_data_dir()
    csv_path = WEB_DATA_DIR / f"{stem}.csv"
    xlsx_path = WEB_DATA_DIR / f"{stem}.xlsx"
    if csv_path.exists():
        try:
            return pd.read_csv(csv_path)
        except Exception:
            return pd.DataFrame()
    if xlsx_path.exists():
        try:
            return pd.read_excel(xlsx_path)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def _append_df_to_csv(path: Path, df: pd.DataFrame) -> None:
    if df.empty:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    header = not path.exists()
    df.to_csv(path, mode="a", index=False, header=header, encoding="utf-8-sig")


def _normalize_web_empresas_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=[
            "empresa_id", "id", "cnpj", "apelido", "razao_social", "nome_fantasia",
            "regime", "cidade", "uf", "contador_responsavel", "ativo",
        ])
    df = df.copy()
    if "empresa_id" not in df.columns and "id" in df.columns:
        df["empresa_id"] = df["id"]
    if "id" not in df.columns and "empresa_id" in df.columns:
        df["id"] = df["empresa_id"]
    for col, default in {
        "cnpj": "",
        "apelido": "",
        "razao_social": "",
        "nome_fantasia": "",
        "regime": "",
        "cidade": "",
        "uf": "",
        "contador_responsavel": "",
        "ativo": 1,
        "atualizado_em": "",
    }.items():
        if col not in df.columns:
            df[col] = default
    df["empresa_id"] = pd.to_numeric(df["empresa_id"], errors="coerce").fillna(0).astype(int)
    df["id"] = df["empresa_id"]
    df["ativo"] = pd.to_numeric(df["ativo"], errors="coerce").fillna(1).astype(int)
    return df


def _normalize_web_demandas_df(df: pd.DataFrame, empresas_df: pd.DataFrame | None = None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=[
            "demanda_id", "id", "empresa_id", "empresa", "apelido", "razao_social", "cnpj",
            "competencia", "tipo_demanda", "descricao", "status", "responsavel_operacional",
            "estagiario_responsavel", "data_limite", "observacao", "concluida_em", "concluida_por",
            "percentual_grupo", "bloqueada", "motivo_bloqueio", "atualizado_em",
        ])
    df = df.copy()
    if "demanda_id" not in df.columns and "id" in df.columns:
        df["demanda_id"] = df["id"]
    if "id" not in df.columns and "demanda_id" in df.columns:
        df["id"] = df["demanda_id"]
    for col in ["empresa_id", "competencia", "tipo_demanda", "descricao", "status", "responsavel_operacional", "estagiario_responsavel", "data_limite", "observacao", "concluida_em", "concluida_por", "motivo_bloqueio", "atualizado_em"]:
        if col not in df.columns:
            df[col] = ""
    if "percentual_grupo" not in df.columns:
        df["percentual_grupo"] = 0.0
    if "bloqueada" not in df.columns:
        df["bloqueada"] = 0
    df["demanda_id"] = pd.to_numeric(df["demanda_id"], errors="coerce").fillna(0).astype(int)
    df["id"] = df["demanda_id"]
    df["empresa_id"] = pd.to_numeric(df["empresa_id"], errors="coerce").fillna(0).astype(int)
    df["bloqueada"] = pd.to_numeric(df["bloqueada"], errors="coerce").fillna(0).astype(int)
    if empresas_df is not None and not empresas_df.empty:
        cols = [c for c in ["empresa_id", "id", "cnpj", "apelido", "razao_social", "nome_fantasia", "regime", "cidade", "uf", "contador_responsavel", "ativo"] if c in empresas_df.columns]
        emp = empresas_df[cols].copy()
        if "id" in emp.columns and "empresa_id" not in emp.columns:
            emp["empresa_id"] = emp["id"]
        df = df.merge(emp.drop_duplicates("empresa_id"), on="empresa_id", how="left", suffixes=("", "_empresa"))
    for col, default in {"apelido": "", "razao_social": "", "cnpj": "", "contador_responsavel": ""}.items():
        if col not in df.columns:
            df[col] = default
    df["empresa"] = df.apply(lambda r: str(r.get("apelido") or r.get("razao_social") or "").strip(), axis=1)
    df["tipo"] = df["tipo_demanda"].fillna("").astype(str)
    df["status_label"] = df["status"].fillna("").astype(str).str.replace("_", " ").str.title()
    df["bloqueio"] = df["motivo_bloqueio"].fillna("").astype(str)
    return df


def load_empresas_from_source(active_only: bool = True) -> pd.DataFrame:
    df = load_web_data()["empresas"].copy()
    df = _normalize_web_empresas_df(df)
    if active_only and not df.empty and "ativo" in df.columns:
        df = df[df["ativo"].astype(int) == 1].copy()
    if not df.empty:
        sort_col = "apelido" if "apelido" in df.columns else "razao_social"
        df = df.sort_values([sort_col, "empresa_id"], na_position="last").reset_index(drop=True)
    return df


def load_usuarios_from_source() -> pd.DataFrame:
    df = load_web_data()["usuarios"].copy()
    if df is None or df.empty:
        return pd.DataFrame(columns=["username", "nome", "perfil", "ativo"])
    df = df.copy()
    for col, default in {"username": "", "nome": "", "perfil": "estagiario", "ativo": 1}.items():
        if col not in df.columns:
            df[col] = default
    df["username"] = df["username"].astype(str).str.upper()
    df["ativo"] = pd.to_numeric(df["ativo"], errors="coerce").fillna(1).astype(int)
    return df


def load_demandas_from_source(competencia: str, filtros: dict | None = None) -> pd.DataFrame:
    df = load_web_data()["demandas"].copy()
    empresas_df = load_empresas_from_source(active_only=False)
    df = _normalize_web_demandas_df(df, empresas_df)
    if df.empty:
        return df
    competencia = str(competencia or "").strip()
    if competencia:
        df = df[df["competencia"].astype(str) == competencia].copy()
    filtros = filtros or {}
    search = str(filtros.get("busca", "") or "").strip().upper()
    if search:
        blob = (
            df["empresa"].fillna("").astype(str)
            + " "
            + df["razao_social"].fillna("").astype(str)
            + " "
            + df["cnpj"].fillna("").astype(str)
            + " "
            + df["tipo_demanda"].fillna("").astype(str)
            + " "
            + df["descricao"].fillna("").astype(str)
        ).str.upper()
        df = df[blob.str.contains(search, regex=False)].copy()
    for key, col in [
        ("tipo", "tipo_demanda"),
        ("status", "status"),
        ("responsavel", "responsavel_operacional"),
        ("estagiario", "estagiario_responsavel"),
        ("empresa", "empresa"),
        ("contador_responsavel", "contador_responsavel"),
    ]:
        value = str(filtros.get(key, "") or "").strip()
        if value and value != "Todos" and col in df.columns:
            df = df[df[col].fillna("").astype(str) == value].copy()
    if filtros.get("minhas"):
        user = normalize_username(current_username())
        if user:
            own = (
                df["responsavel_operacional"].fillna("").astype(str).str.upper().eq(user)
                | df["estagiario_responsavel"].fillna("").astype(str).str.upper().eq(user)
            )
            df = df[own].copy()
    if filtros.get("mostrar_concluidas") is False:
        df = df[~df["status"].astype(str).isin(["concluida", "dispensada", "cancelada"])].copy()
    if filtros.get("atrasadas"):
        hoje = date.today().isoformat()
        df["atrasada"] = df.apply(
            lambda row: bool(str(row.get("data_limite") or "").strip() and str(row.get("data_limite")) < hoje and str(row.get("status")) not in {"concluida", "dispensada", "cancelada"}),
            axis=1,
        )
        df = df[df["atrasada"]].copy()
    if "percentual_grupo" not in df.columns:
        df["percentual_grupo"] = df.groupby(["empresa_id", "competencia"])["status"].transform(
            lambda s: round(100.0 * (s.astype(str) == "concluida").sum() / max(len(s), 1), 2)
        )
    if "atrasada" not in df.columns:
        hoje = date.today().isoformat()
        df["atrasada"] = df.apply(
            lambda row: bool(str(row.get("data_limite") or "").strip() and str(row.get("data_limite")) < hoje and str(row.get("status")) not in {"concluida", "dispensada", "cancelada"}),
            axis=1,
        )
    return df.reset_index(drop=True)


def can_user_mark_demanda(username: str, demanda: dict | pd.Series) -> bool:
    user = normalize_username(username)
    if not user:
        return False
    if is_admin_geral() or is_contador():
        return True
    if isinstance(demanda, pd.Series):
        demanda = demanda.to_dict()
    if not isinstance(demanda, dict):
        return False
    responsavel = normalize_username(demanda.get("estagiario_responsavel") or demanda.get("responsavel_operacional"))
    return bool(responsavel and responsavel == user)


def append_web_action_log(username: str, acao: str, entidade: str = "", entidade_id: int | None = None, detalhe: str = "") -> None:
    row = pd.DataFrame([{
        "username": normalize_username(username),
        "acao": str(acao or "").strip(),
        "entidade": str(entidade or "").strip(),
        "entidade_id": int(entidade_id or 0),
        "detalhe": str(detalhe or "").strip(),
        "data_hora": datetime.now().isoformat(timespec="seconds"),
    }])
    _append_df_to_csv(WEB_ACTION_LOG_CSV_PATH, row)
    try:
        _ensure_web_data_dir()
        with sqlite3.connect(str(WEB_DATA_SQLITE_PATH)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS logs_web (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT,
                    acao TEXT NOT NULL,
                    entidade TEXT,
                    entidade_id INTEGER DEFAULT 0,
                    detalhe TEXT,
                    data_hora TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT INTO logs_web (username, acao, entidade, entidade_id, detalhe, data_hora) VALUES (?, ?, ?, ?, ?, ?)",
                tuple(row.iloc[0][["username", "acao", "entidade", "entidade_id", "detalhe", "data_hora"]]),
            )
            conn.commit()
    except Exception:
        pass


def save_demanda_status_to_source(demanda_id: int, status: str, observacao: str = "", username: str | None = None) -> None:
    user = normalize_username(username or current_username() or "WEB")
    status_norm = str(status or "").strip().lower() or "pendente"
    observacao = str(observacao or "").strip()
    now = datetime.now().isoformat(timespec="seconds")
    _ensure_web_data_dir()
    try:
        with sqlite3.connect(str(WEB_DATA_SQLITE_PATH)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS demandas_web (
                    demanda_id INTEGER PRIMARY KEY,
                    empresa_id INTEGER NOT NULL,
                    competencia TEXT,
                    tipo_demanda TEXT,
                    descricao TEXT,
                    status TEXT,
                    responsavel_operacional TEXT,
                    estagiario_responsavel TEXT,
                    data_limite TEXT,
                    observacao TEXT,
                    concluida_em TEXT,
                    concluida_por TEXT,
                    percentual_grupo REAL DEFAULT 0,
                    bloqueada INTEGER DEFAULT 0,
                    motivo_bloqueio TEXT,
                    atualizado_em TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS marcacoes_web (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    demanda_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    acao TEXT NOT NULL,
                    status_novo TEXT,
                    observacao TEXT,
                    data_hora TEXT NOT NULL,
                    processed INTEGER DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                UPDATE demandas_web
                   SET status=?,
                       observacao=CASE WHEN COALESCE(?, '') <> '' THEN ? ELSE observacao END,
                       concluida_em=CASE WHEN ? = 'concluida' THEN COALESCE(concluida_em, ?) ELSE concluida_em END,
                       concluida_por=CASE WHEN ? = 'concluida' THEN COALESCE(concluida_por, ?) ELSE concluida_por END,
                       atualizado_em=?
                 WHERE demanda_id=?
                """,
                (
                    status_norm,
                    observacao,
                    observacao,
                    status_norm,
                    now,
                    status_norm,
                    user,
                    now,
                    int(demanda_id),
                ),
            )
            conn.execute(
                "INSERT INTO marcacoes_web (demanda_id, username, acao, status_novo, observacao, data_hora, processed) VALUES (?, ?, ?, ?, ?, ?, 0)",
                (int(demanda_id), user, "status", status_norm, observacao, now),
            )
            conn.commit()
    except Exception:
        pass

    try:
        demandas_df = load_web_data()["demandas"].copy()
        if demandas_df is None or demandas_df.empty:
            demandas_df = _load_web_csv_or_excel("demandas_web")
        empresas_df = load_empresas_from_source(active_only=False)
        demandas_df = _normalize_web_demandas_df(demandas_df, empresas_df)
        if not demandas_df.empty and "demanda_id" in demandas_df.columns:
            mask = demandas_df["demanda_id"].astype(int) == int(demanda_id)
            if mask.any():
                demandas_df.loc[mask, "status"] = status_norm
                if observacao:
                    demandas_df.loc[mask, "observacao"] = observacao
                if status_norm == "concluida":
                    demandas_df.loc[mask, "concluida_em"] = now
                    demandas_df.loc[mask, "concluida_por"] = user
                demandas_df.loc[mask, "atualizado_em"] = now
                demandas_df.to_csv(WEB_DEMANDAS_CSV_PATH, index=False, encoding="utf-8-sig")
    except Exception:
        pass

    _append_df_to_csv(WEB_MARCACOES_CSV_PATH, pd.DataFrame([{
        "demanda_id": int(demanda_id),
        "username": user,
        "acao": "status",
        "status_novo": status_norm,
        "observacao": observacao,
        "data_hora": now,
    }]))
    append_web_action_log(user, "ALTERAR_STATUS", "demandas_web", int(demanda_id), f"status={status_norm}")
    try:
        load_web_data.clear()
    except Exception:
        pass


def render_module_locked(title: str) -> None:
    st.subheader(title)
    st.info("Modulo em desenvolvimento. Nesta fase, o sistema Web funciona apenas para Empresas e Demandas.")


def apply_nexus_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
            --nexus-bg: #f4f7fb;
            --nexus-surface: #ffffff;
            --nexus-surface-2: #eef2ff;
            --nexus-border: #d6deea;
            --nexus-primary: #5b21b6;
            --nexus-accent: #7c3aed;
            --nexus-text: #0f172a;
            --nexus-muted: #475569;
            --nexus-danger: #dc2626;
            --nexus-ok: #059669;
            --nexus-warn: #d97706;
        }
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(124,58,237,.10), transparent 34%),
                radial-gradient(circle at top right, rgba(37,99,235,.08), transparent 30%),
                linear-gradient(180deg, #f8fbff 0%, #f4f7fb 38%, #eef3f9 100%);
            background-size: auto;
            color: var(--nexus-text);
            opacity: 1 !important;
            filter: none !important;
        }
        .stApp[aria-busy="true"],
        .stApp[aria-busy="true"] *,
        div[data-testid="stAppViewContainer"],
        div[data-testid="stAppViewContainer"] * {
            opacity: 1 !important;
            filter: none !important;
        }
        header[data-testid="stHeader"] {
            background-color: transparent !important;
        }
        div[data-testid="stToolbar"],
        .stDeployButton {
            display: none !important;
        }
        [data-testid="stDecoration"] {
            display: none !important;
        }
        .block-container {
            padding-top: 0.15rem;
            max-width: 1280px;
        }
        h1 {
            margin-bottom: 0.45rem !important;
        }
        h2, h3 {
            margin-bottom: 0.35rem !important;
        }
        div[data-testid="stCaptionContainer"] {
            margin-top: 0.1rem !important;
            margin-bottom: 0.15rem !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            margin-bottom: 0.65rem !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] > div {
            padding-top: 0.2rem !important;
            padding-bottom: 0.2rem !important;
        }
        section[data-testid="stSidebar"] .element-container {
            margin-bottom: 0.02rem !important;
        }
        section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
            margin-bottom: 0 !important;
        }
        section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
            margin-top: 0 !important;
            margin-bottom: 0 !important;
        }
        section[data-testid="stSidebar"] hr {
            margin: 0.12rem 0 !important;
        }
        section[data-testid="stSidebar"] {
            width: 16rem !important;
            min-width: 16rem !important;
            max-width: 16rem !important;
        }
        .sidebar-logo {
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 0 2px 2px 2px;
        }
        .sidebar-logo img {
            max-width: 76px !important;
            height: auto !important;
            object-fit: contain !important;
            display: block;
            margin: 0 auto 1px auto;
        }
        section[data-testid="stSidebar"] {
            background:
                linear-gradient(135deg, rgba(91,33,182,.05) 0 1px, transparent 1px 18px),
                #f8fbff;
            background-size: 18px 18px, auto;
            border-right: 1px solid var(--nexus-border);
        }
        section[data-testid="stSidebar"] * {
            color: var(--nexus-text) !important;
            opacity: 1 !important;
        }
        section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] span {
            color: var(--nexus-text) !important;
            opacity: 1 !important;
        }
        section[data-testid="stSidebar"] small,
        section[data-testid="stSidebar"] .stCaptionContainer {
            color: var(--nexus-muted) !important;
            opacity: 1 !important;
        }
        h1, h2, h3 {
            color: var(--nexus-text) !important;
            letter-spacing: 0;
        }
        h1 {
            font-size: 2rem !important;
            line-height: 1.1 !important;
        }
        h2 {
            font-size: 1.35rem !important;
            line-height: 1.15 !important;
        }
        h3 {
            font-size: 1.1rem !important;
            line-height: 1.15 !important;
        }
        p, label, span, div {
            letter-spacing: 0;
        }
        div[data-testid="stMetric"] {
            background: rgba(255,255,255,.92);
            border: 1px solid var(--nexus-border);
            border-radius: 12px;
            padding: 10px 14px;
            box-shadow: 0 14px 28px rgba(15,23,42,.08);
        }
        div[data-testid="stMetric"] label, div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            color: var(--nexus-text) !important;
        }
        div[data-testid="stDataFrame"], div[data-testid="stForm"], div[data-testid="stExpander"] {
            border-radius: 12px;
        }
        div[data-testid="stExpander"] {
            margin-bottom: 0.6rem !important;
        }
        div[data-testid="stExpander"] summary {
            padding-top: 0.35rem !important;
            padding-bottom: 0.35rem !important;
        }
        div[data-testid="stExpander"] div[role="button"] {
            min-height: 2rem !important;
        }
        .stButton > button, .stDownloadButton > button, div[data-testid="stFormSubmitButton"] button {
            background: var(--nexus-primary);
            color: white;
            border: 1px solid rgba(255,255,255,.10);
            border-radius: 10px;
            font-weight: 700;
            box-shadow: 0 10px 24px rgba(86,0,178,.22);
        }
        .stButton > button:hover, .stDownloadButton > button:hover, div[data-testid="stFormSubmitButton"] button:hover {
            background: var(--nexus-accent);
            color: white;
            border-color: rgba(255,255,255,.20);
        }
        .stButton > button[data-testid="stBaseButton-secondary"], 
        .stDownloadButton > button[data-testid="stBaseButton-secondary"] {
            background: #ffffff !important;
            color: var(--nexus-primary) !important;
            border: 1px solid var(--nexus-border) !important;
            box-shadow: 0 4px 12px rgba(15,23,42,.04) !important;
        }
        .stButton > button[data-testid="stBaseButton-secondary"]:hover, 
        .stDownloadButton > button[data-testid="stBaseButton-secondary"]:hover {
            background: rgba(91,33,182,.04) !important;
            color: var(--nexus-accent) !important;
            border-color: var(--nexus-primary) !important;
        }
        input, textarea, select {
            background-color: #ffffff !important;
            color: var(--nexus-text) !important;
            border-color: var(--nexus-border) !important;
            border-radius: 10px !important;
        }
        div[data-baseweb="select"] * {
            color: var(--nexus-text) !important;
        }
        div[data-testid="stDataFrame"] {
            background: #ffffff;
            color: #0f172a;
            border: 1px solid var(--nexus-border);
        }
        div[data-testid="stDataFrame"] * {
            color: #0f172a;
        }
        div[data-testid="stAlert"] {
            color: #0f172a;
        }
        div[data-testid="stAlert"] * {
            color: #0f172a !important;
        }
        div[data-testid="stFileUploader"] section {
            background: #ffffff;
            color: #0f172a;
            border-radius: 10px;
        }
        div[data-testid="stFileUploader"] section * {
            color: #0f172a !important;
        }
        div[data-testid="stSidebar"] .stButton > button,
        div[data-testid="stSidebar"] .stLinkButton > a {
            background: #5b21b6 !important;
            color: #ffffff !important;
            border: 1px solid #7c3aed !important;
            font-weight: 800 !important;
            box-shadow: 0 10px 22px rgba(86, 0, 178, .26) !important;
        }
        div[data-testid="stSidebar"] .stButton > button *,
        div[data-testid="stSidebar"] .stLinkButton > a * {
            color: #ffffff !important;
            opacity: 1 !important;
        }
        div[data-testid="stSidebar"] .stButton > button:hover,
        div[data-testid="stSidebar"] .stLinkButton > a:hover {
            background: #7c3aed !important;
        }
        section[data-testid="stSidebar"] a[href="http://localhost:8501/"] {
            background: #5b21b6 !important;
            color: #ffffff !important;
            border: 1px solid #7c3aed !important;
        }
        section[data-testid="stSidebar"] a[href="http://localhost:8501/"] * {
            color: #ffffff !important;
        }
        div[data-testid="stSidebar"] input {
            background-color: #ffffff !important;
            color: var(--nexus-text) !important;
        }
        div[data-testid="stSidebar"] .stButton > button,
        div[data-testid="stSidebar"] .stLinkButton > a {
            min-height: 1.9rem !important;
            padding: 0.18rem 0.48rem !important;
            font-size: 0.88rem !important;
        }
        div[data-testid="stSidebar"] .stSelectbox,
        div[data-testid="stSidebar"] .stRadio {
            margin-bottom: 0.05rem !important;
        }
        div[data-testid="stSidebar"] [data-testid="stRadio"] {
            margin-top: 0.05rem !important;
            margin-bottom: 0.05rem !important;
        }
        div[data-testid="stSidebar"] [data-testid="stRadio"] label {
            margin-bottom: 0.02rem !important;
        }
        .top-action-row .stButton > button {
            width: 100% !important;
            min-height: 3.1rem !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        .nexus-topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            padding: 12px 16px;
            margin: 12px 0 20px;
            background: rgba(255,255,255,.90);
            border: 1px solid var(--nexus-border);
            border-radius: 12px;
            box-shadow: 0 10px 24px rgba(15,23,42,.06);
        }
        .global-menu-panel {
            padding: 6px 4px 2px 4px;
        }
        .global-menu-panel .stButton > button {
            width: 100% !important;
            min-width: 0 !important;
            max-width: none !important;
            min-height: 46px !important;
            padding: 0.55rem 0.75rem !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            text-align: center !important;
            border-radius: 12px !important;
            box-sizing: border-box !important;
            cursor: pointer !important;
        }
        .global-menu-panel .stButton > button p {
            width: 100%;
            text-align: center !important;
            pointer-events: none !important;
            margin: 0 !important;
            line-height: 1.1 !important;
        }
        .global-menu-panel .stButton > button span {
            pointer-events: none !important;
        }
        .login-brand {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 14px;
            color: var(--nexus-text);
            font-size: 12px;
            font-weight: 900;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }
        .login-mark {
            width: 34px;
            height: 34px;
            display: inline-grid;
            place-items: center;
            border-radius: 10px;
            background: linear-gradient(135deg, #6d28d9 0%, #7c3aed 48%, #4f46e5 100%);
            color: #fff;
            box-shadow: 0 14px 28px rgba(91,33,182,.28);
        }
        .login-title {
            font-size: 28px;
            line-height: 1.06;
            font-weight: 900;
            color: var(--nexus-text);
            margin: 0 0 6px 0;
            letter-spacing: 0;
        }
        .login-subtitle {
            color: var(--nexus-muted);
            font-size: 13px;
            margin-bottom: 18px;
            max-width: 34ch;
        }
        .st-key-login_card,
        .st-key-login_card_secure {
            width: min(392px, calc(100vw - 32px));
            margin: 8vh auto 0 auto;
            background:
                linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(248,250,255,.98) 100%);
            border: 1px solid rgba(91,33,182,.18);
            outline: 1px solid rgba(91,33,182,.06);
            border-radius: 22px;
            padding: 20px 20px 18px;
            box-shadow:
                0 24px 60px rgba(15,23,42,.12),
                0 2px 0 rgba(255,255,255,.75) inset;
        }
        .st-key-login_card div[data-testid="stForm"],
        .st-key-login_card_secure div[data-testid="stForm"] {
            border: 0;
            padding: 0;
        }
        .st-key-login_card input,
        .st-key-login_card_secure input {
            min-height: 40px;
        }
        .st-key-login_card div[data-testid="stTextInputRootElement"],
        .st-key-login_card_secure div[data-testid="stTextInputRootElement"] {
            margin-bottom: 0.35rem;
            background: #ffffff !important;
            border: 1px solid rgba(91,33,182,.18) !important;
            border-radius: 12px !important;
            box-shadow: 0 1px 0 rgba(15,23,42,.03) inset;
            padding: 0.08rem 0.3rem !important;
        }
        .st-key-login_card div[data-testid="stTextInputRootElement"]:focus-within,
        .st-key-login_card_secure div[data-testid="stTextInputRootElement"]:focus-within {
            border-color: rgba(91,33,182,.58) !important;
            box-shadow: 0 0 0 3px rgba(91,33,182,.12) !important;
        }
        .st-key-login_card div[data-testid="stTextInputRootElement"] input,
        .st-key-login_card_secure div[data-testid="stTextInputRootElement"] input {
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
            padding: 0.28rem 0.35rem !important;
            min-height: 30px !important;
        }
        .st-key-login_card label,
        .st-key-login_card_secure label {
            margin-bottom: 0.14rem !important;
            font-weight: 700 !important;
            color: var(--nexus-text) !important;
            font-size: 13px !important;
        }
        .st-key-login_card .stButton > button,
        .st-key-login_card div[data-testid="stFormSubmitButton"] button,
        .st-key-login_card_secure .stButton > button,
        .st-key-login_card_secure div[data-testid="stFormSubmitButton"] button {
            width: 100%;
            min-height: 42px;
            border-radius: 12px;
            border: 0;
            background: linear-gradient(135deg, #6d28d9 0%, #7c3aed 55%, #4f46e5 100%);
            color: #fff;
            box-shadow: 0 16px 28px rgba(91,33,182,.22);
            font-weight: 800;
            letter-spacing: 0.02em;
        }
        .st-key-login_card .stButton > button:hover,
        .st-key-login_card div[data-testid="stFormSubmitButton"] button:hover,
        .st-key-login_card_secure .stButton > button:hover,
        .st-key-login_card_secure div[data-testid="stFormSubmitButton"] button:hover {
            filter: brightness(1.03);
            transform: translateY(-1px);
        }
        .nexus-brand {
            font-size: 14px;
            font-weight: 900;
            text-transform: uppercase;
        }
        .nexus-brand span {
            color: #8b5cf6;
        }
        .nexus-local-link {
            color: #5b21b6 !important;
            text-decoration: none;
            font-weight: 700;
        }
        .nexus-module-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 12px;
            margin-top: 10px;
        }
        .nexus-module {
            display: block;
            background: rgba(255,255,255,.95);
            border: 1px solid var(--nexus-border);
            border-radius: 12px;
            padding: 14px;
            min-height: 120px;
            color: inherit;
            text-decoration: none;
            transition: transform .16s ease, border-color .16s ease, background .16s ease, box-shadow .16s ease;
        }
        a.nexus-module {
            cursor: pointer;
        }
        a.nexus-module:hover {
            transform: translateY(-2px);
            background: #ffffff;
            border-color: rgba(124,58,237,.48);
            box-shadow: 0 18px 34px rgba(15,23,42,.10), 0 0 0 1px rgba(124,58,237,.08) inset;
            text-decoration: none;
        }
        .nexus-module.disabled {
            cursor: default;
            opacity: .78;
        }
        .nexus-module strong {
            display: block;
            color: var(--nexus-text);
            margin-bottom: 4px;
        }
        .nexus-module small {
            color: var(--nexus-muted);
        }
        .nexus-status {
            display: inline-block;
            margin-top: 10px;
            padding: 3px 8px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 800;
            text-transform: uppercase;
        }
        .nexus-status.ok {
            background: rgba(5,150,105,.10);
            color: var(--nexus-ok);
            border: 1px solid rgba(5,150,105,.22);
        }
        .nexus-status.pending {
            background: rgba(217,119,6,.10);
            color: var(--nexus-warn);
            border: 1px solid rgba(217,119,6,.22);
        }
        div[class*="st-key-module_btn_"] button {
            width: 100%;
            min-height: 116px;
            justify-content: flex-start;
            align-items: flex-start;
            text-align: left;
            white-space: pre-line;
            padding: 18px 18px 14px;
            background: #ffffff !important;
            border: 1px solid var(--nexus-border) !important;
            border-top: 4px solid #6aa0ff !important;
            border-radius: 12px !important;
            color: var(--nexus-text) !important;
            box-shadow: none;
            line-height: 1.45;
        }
        div[class*="st-key-module_btn_"] button p {
            color: var(--nexus-text) !important;
            font-weight: 700;
        }
        div[class*="st-key-module_btn_"] button:hover:not(:disabled) {
            transform: translateY(-1px);
            background: #f8fbff !important;
            border-color: #8bb6ff !important;
            box-shadow: 0 18px 34px rgba(15,23,42,.08), 0 0 0 1px rgba(139,182,255,.14) inset;
        }
        div[class*="st-key-module_btn_"] button:disabled {
            background: rgba(241,245,249,.92) !important;
            border-color: rgba(148,163,184,.28) !important;
            border-top-color: rgba(148,163,184,.28) !important;
            opacity: .90;
            cursor: default;
        }
        div[class*="st-key-module_btn_"] button:disabled p {
            color: #94a3b8 !important;
        }
        div[class*="st-key-module_btn_Painel_de_Controle_2026"] button {
            border-color: #6aa0ff !important;
            border-top-color: #6aa0ff !important;
        }
        .launcher-shell {
            max-width: 1160px;
            padding: 0 0 10px;
            background: transparent;
            border: 0;
            box-shadow: none;
        }
        .launcher-kicker {
            color: var(--nexus-muted);
            font-size: 12px;
            font-weight: 800;
            text-transform: uppercase;
            margin-bottom: 10px;
        }
        .launcher-title {
            color: var(--nexus-text);
            font-size: 28px;
            line-height: 1.1;
            font-weight: 900;
            margin-bottom: 6px;
        }
        .launcher-subtitle {
            color: var(--nexus-muted);
            font-size: 14px;
            margin-bottom: 10px;
        }
        .launcher-grid-wrap {
            max-width: 920px;
        }
        .module-card {
            min-height: 132px;
            padding: 16px 16px 14px;
            margin-bottom: 16px;
            background: #ffffff;
            border: 1px solid var(--nexus-border);
            border-top: 4px solid #6aa0ff;
            box-shadow: 0 14px 30px rgba(15,23,42,.08);
        }
        .module-card.disabled {
            background: #f8fafc;
            border-color: rgba(148,163,184,.30);
            border-top-color: rgba(148,163,184,.30);
            box-shadow: none;
        }
        .module-head {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 10px;
        }
        .module-icon {
            width: 26px;
            height: 26px;
            display: inline-grid;
            place-items: center;
            background: #dbeafe;
            color: #1d4ed8;
            font-weight: 900;
        }
        .module-title {
            color: var(--nexus-text);
            font-size: 16px;
            font-weight: 900;
            flex: 1;
        }
        .module-tag {
            color: #0f172a;
            background: #6aa0ff;
            font-family: Consolas, monospace;
            font-size: 10px;
            font-weight: 900;
            padding: 4px 10px;
            text-transform: uppercase;
        }
        .module-card.disabled .module-icon,
        .module-card.disabled .module-tag {
            background: rgba(148,163,184,.18);
            color: #334155;
        }
        .module-card.disabled .module-title,
        .module-card.disabled .module-desc {
            color: var(--nexus-muted);
        }
        .module-desc {
            min-height: 40px;
            color: var(--nexus-muted);
            font-size: 13px;
            line-height: 1.45;
        }
        div[class*="st-key-module_open_"] button {
            min-height: 42px !important;
            padding: 0.4rem 0.85rem !important;
            border-radius: 10px !important;
            font-weight: 800 !important;
        }
        div[class*="st-key-module_disabled_"] button {
            min-height: 42px !important;
            padding: 0.4rem 0.85rem !important;
            border-radius: 10px !important;
            font-weight: 800 !important;
            cursor: default !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_company_logo(width: int = 86, location: str = "sidebar") -> None:
    if LOGO_PATH.exists():
        logo_bytes = LOGO_PATH.read_bytes()
        logo_b64 = base64.b64encode(logo_bytes).decode("ascii")
        st.markdown(
            f"""
            <div class="sidebar-logo">
                <img src="data:image/png;base64,{logo_b64}" alt="Excelencia Contabilidade" width="{width}" />
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="sidebar-logo"><div style="text-align:center; font-weight:800; letter-spacing:0.04em;">EXCELENCIA CONTABILIDADE</div></div>',
            unsafe_allow_html=True,
        )


def normalize_page(page: str) -> str:
    page_txt = str(page or "").strip()
    aliases = {
        "Automação": "Automacao",
        "Automacao": "Automacao",
        "Faturamento": "Faturamento MEI",
        "Faturamento MEI": "Faturamento MEI",
        "Módulos": "Modulos",
        "Modulos": "Modulos",
        "Painel de Controle 2026": "Painel",
    }
    return aliases.get(page_txt, page_txt)


def normalize_page(page: str) -> str:
    page_txt = str(page or "").strip()
    aliases = {
        "Automação": "Automacao",
        "AutomaÃ§Ã£o": "Automacao",
        "Automacao": "Automacao",
        "Faturamento": "Faturamento",
        "Faturamento MEI": "Faturamento",
        "Módulos": "Modulos",
        "MÃ³dulos": "Modulos",
        "Modulos": "Modulos",
        "Painel de Controle 2026": "Painel",
    }
    return aliases.get(page_txt, page_txt)


def render_topbar() -> None:
    if "global_menu_open" not in st.session_state:
        st.session_state["global_menu_open"] = False

    cols = st.columns([7.0, 1.0, 1.2], vertical_alignment="center")
    cols[0].markdown(
        """
        <div class="nexus-topbar">
            <div class="nexus-brand">EXCELENCIA <span>CONTABILIDADE</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if cols[1].button("?? Voltar", key="topbar_back", use_container_width=True):
        go_back()
    if cols[2].button("? Menu", key="global_menu_toggle", use_container_width=True):
        st.session_state["global_menu_open"] = not st.session_state.get("global_menu_open", False)

    if st.session_state.get("global_menu_open", False):
        st.markdown('<div class="global-menu-panel">', unsafe_allow_html=True)
        with st.container(border=True):
            st.caption(f"Navegacao global - pagina atual: {st.session_state.get('page_label', '?? M?dulos')}")
            items = list(NAV_MENU.items())
            for start in range(0, len(items), 4):
                row = items[start:start + 4]
                row_cols = st.columns(len(row))
                for idx, (label, page) in enumerate(row):
                    button_type = "primary" if st.session_state.get("page") == page else "secondary"
                    with row_cols[idx]:
                        if st.button(label, key=f"global_menu_{page}", type=button_type, use_container_width=False):
                            st.session_state["global_menu_open"] = False
                            navigate_to(page, label)
        st.markdown("</div>", unsafe_allow_html=True)


def navigate_to(page: str, label: str | None = None, push_history: bool = True) -> None:
    page = normalize_page(page)
    current = str(st.session_state.get("page") or "").strip()
    if push_history and current and current != page:
        history = st.session_state.setdefault("nav_history", [])
        if not history or history[-1] != current:
            history.append(current)
        st.session_state["nav_history"] = history[-20:]
    if label is None:
        label = next((menu_label for menu_label, menu_page in NAV_MENU.items() if menu_page == page), page)
    st.session_state["page"] = page
    st.session_state["page_label"] = label
    st.session_state["_nav_override_page"] = page
    st.query_params["page"] = page
    st.rerun()


def set_navigation_target(page: str, label: str | None = None, push_history: bool = True) -> None:
    page = normalize_page(page)
    current = str(st.session_state.get("page") or "").strip()
    if push_history and current and current != page:
        history = st.session_state.setdefault("nav_history", [])
        if not history or history[-1] != current:
            history.append(current)
        st.session_state["nav_history"] = history[-20:]
    if label is None:
        label = next((menu_label for menu_label, menu_page in NAV_MENU.items() if menu_page == page), page)
    st.session_state["page"] = page
    st.session_state["page_label"] = label
    st.session_state["_nav_override_page"] = page
    st.query_params["page"] = page


def go_back() -> None:
    history = st.session_state.get("nav_history", [])
    if history:
        previous = history.pop()
        st.session_state["nav_history"] = history
        navigate_to(previous, next((menu_label for menu_label, menu_page in NAV_MENU.items() if menu_page == previous), previous), push_history=False)
    else:
        navigate_to("Modulos", "📂 Módulos", push_history=False)


def navigate_to_page(page: str, page_label: str | None = None) -> None:
    if page_label is None:
        page_label = next((label for label, value in NAV_MENU.items() if value == page), page)
    navigate_to(page, page_label)


def normalize_username(value: str) -> str:
    return str(value or "").strip().upper()


def current_username() -> str:
    return normalize_username(
        st.session_state.get("username")
        or st.session_state.get("auth_user")
        or st.session_state.get("user")
        or ""
    )


def current_user_role() -> str:
    return str(st.session_state.get("user_role") or "").strip() or "usuario"


def current_user_display_name() -> str:
    value = str(st.session_state.get("user_name") or "").strip()
    return value or current_username() or "sistema"


def user_role_label(role: str) -> str:
    return USER_ROLES.get(str(role or "").strip(), str(role or "").strip() or "Usuário")


def is_admin_geral() -> bool:
    return current_username() == "DMLIMA" or current_user_role() == "admin_geral"


def is_contador() -> bool:
    return current_username() == "RAFAEL" or current_user_role() in {"contador", "admin_geral"}


def can_manage_users() -> bool:
    return current_username() in USER_MANAGEMENT_ALLOWED or is_admin_geral()


def can_access_users_page() -> bool:
    return can_manage_users()


def can_manage_user(target_user) -> bool:
    if is_admin_geral():
        return True
    if not is_contador():
        return False
    target = target_user
    if isinstance(target_user, pd.Series):
        target = target_user.to_dict()
    if isinstance(target, dict):
        target_username = normalize_username(target.get("username"))
        target_role = str(target.get("role") or "usuario").strip() or "usuario"
        responsavel = normalize_username(target.get("responsavel"))
        criado_por = normalize_username(target.get("criado_por"))
    else:
        target_username = normalize_username(target)
        target_role = "usuario"
        responsavel = ""
        criado_por = ""
    if target_username in {"DMLIMA"}:
        return False
    if target_role in {"admin_geral", "contador"} and target_username != "RAFAEL":
        return False
    if target_username == "RAFAEL":
        return True
    return current_username() in {responsavel, criado_por}


def hash_password(password: str) -> str:
    raw_password = str(password or "")
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        raw_password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, senha_hash: str) -> bool:
    raw_hash = str(senha_hash or "").strip()
    if not raw_hash or "$" not in raw_hash:
        return False
    try:
        algorithm, iterations, salt_hex, digest_hex = raw_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            str(password or "").encode("utf-8"),
            salt,
            int(iterations),
        )
        return hmac.compare_digest(candidate, expected)
    except Exception:
        return False


def load_legacy_auth_users() -> dict[str, str]:
    users: dict[str, str] = {}
    if AUTH_EXPORT_PATH.exists():
        try:
            data = tomllib.loads(AUTH_EXPORT_PATH.read_text(encoding="utf-8"))
            raw_users = data.get("auth", {}).get("users", {})
            users.update({normalize_username(k): str(v) for k, v in dict(raw_users).items()})
        except Exception:
            pass
    try:
        secrets_auth = st.secrets.get("auth", {})
        raw_users = secrets_auth.get("users", {}) if hasattr(secrets_auth, "get") else {}
        users.update({normalize_username(k): str(v) for k, v in dict(raw_users).items()})
    except Exception:
        pass
    env_user = normalize_username(os.getenv("CONTROLE_EMPRESAS_USER"))
    env_password = os.getenv("CONTROLE_EMPRESAS_PASSWORD")
    if env_user and env_password:
        users[env_user] = str(env_password)
    return users


def configured_users() -> dict[str, str]:
    return load_legacy_auth_users()


def user_role_for(username: str, default_role: str = "usuario") -> str:
    username_norm = normalize_username(username)
    if username_norm in SPECIAL_USER_ROLES:
        return SPECIAL_USER_ROLES[username_norm]
    role = str(default_role or "usuario").strip()
    return role if role in USER_ROLES else "usuario"


def user_display_name_for(username: str, stored_name: str = "") -> str:
    name = str(stored_name or "").strip()
    return name or normalize_username(username) or "Usuário"


def get_user_row(username: str):
    username_norm = normalize_username(username)
    if not username_norm:
        return None
    df = query_df("SELECT * FROM users WHERE UPPER(username)=UPPER(?) LIMIT 1", (username_norm,))
    if df.empty:
        return None
    return df.iloc[0].to_dict()


def get_users_df() -> pd.DataFrame:
    return query_df(
        """
        SELECT id, username, COALESCE(nome,'') AS nome, COALESCE(role,'usuario') AS role,
               COALESCE(ativo,1) AS ativo, COALESCE(responsavel,'') AS responsavel,
               COALESCE(criado_por,'') AS criado_por, COALESCE(criado_em,'') AS criado_em,
               COALESCE(atualizado_em,'') AS atualizado_em, COALESCE(ultimo_login,'') AS ultimo_login,
               COALESCE(observacao,'') AS observacao
          FROM users
         ORDER BY username COLLATE NOCASE
        """
    )


def get_visible_users_df() -> pd.DataFrame:
    df = get_users_df()
    if df.empty:
        return df
    if is_admin_geral():
        return df
    if current_username() == "RAFAEL":
        mask = (
            df["username"].astype(str).str.upper().eq("RAFAEL")
            | df["responsavel"].astype(str).str.upper().eq("RAFAEL")
            | df["criado_por"].astype(str).str.upper().eq("RAFAEL")
        )
        return df.loc[mask].copy()
    return df.iloc[0:0].copy()


def active_admin_count() -> int:
    df = query_df(
        """
        SELECT COUNT(*) AS total
          FROM users
         WHERE COALESCE(ativo,1)=1
           AND COALESCE(role,'usuario')='admin_geral'
        """
    )
    if df.empty:
        return 0
    return int(df.iloc[0]["total"] or 0)


def can_disable_user_record(target: dict) -> bool:
    username_norm = normalize_username(target.get("username"))
    role = str(target.get("role") or "usuario")
    ativo = int(target.get("ativo") or 0)
    if ativo == 0:
        return True
    if username_norm == "DMLIMA" and active_admin_count() <= 1:
        return False
    if role == "admin_geral" and active_admin_count() <= 1:
        return False
    return True


def upsert_user_record(
    *,
    username: str,
    nome: str,
    senha_hash: str,
    role: str,
    ativo: int = 1,
    criado_por: str = "",
    responsavel: str = "",
    observacao: str = "",
    criado_em: str | None = None,
    atualizado_em: str | None = None,
    ultimo_login: str | None = None,
) -> None:
    username_norm = normalize_username(username)
    role_norm = user_role_for(username_norm, role)
    responsavel_norm = normalize_username(responsavel) or username_norm
    criado_por_norm = normalize_username(criado_por)
    timestamp = now_str()
    created_at = criado_em or timestamp
    updated_at = atualizado_em or timestamp
    execute(
        """
        INSERT INTO users (username, nome, senha_hash, role, ativo, criado_por, responsavel, observacao, criado_em, atualizado_em, ultimo_login)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(username) DO UPDATE SET
            nome=excluded.nome,
            senha_hash=COALESCE(NULLIF(excluded.senha_hash,''), users.senha_hash),
            role=excluded.role,
            ativo=excluded.ativo,
            criado_por=COALESCE(NULLIF(excluded.criado_por,''), users.criado_por),
            responsavel=COALESCE(NULLIF(excluded.responsavel,''), users.responsavel),
            observacao=excluded.observacao,
            criado_em=COALESCE(users.criado_em, excluded.criado_em),
            atualizado_em=excluded.atualizado_em,
            ultimo_login=COALESCE(NULLIF(excluded.ultimo_login,''), users.ultimo_login)
        """,
        (
            username_norm,
            str(nome or "").strip() or username_norm,
            str(senha_hash or "").strip(),
            role_norm,
            int(1 if ativo else 0),
            criado_por_norm,
            responsavel_norm,
            str(observacao or "").strip(),
            created_at,
            updated_at,
            str(ultimo_login or "").strip(),
        ),
    )


def ensure_user_schema() -> None:
    if using_postgres():
        execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                nome TEXT,
                senha_hash TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'usuario',
                ativo INTEGER DEFAULT 1,
                criado_em TEXT,
                atualizado_em TEXT,
                criado_por TEXT,
                responsavel TEXT,
                observacao TEXT,
                ultimo_login TEXT
            )
            """
        )
    else:
        with get_sqlite_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    nome TEXT,
                    senha_hash TEXT NOT NULL DEFAULT '',
                    role TEXT NOT NULL DEFAULT 'usuario',
                    ativo INTEGER DEFAULT 1,
                    criado_em TEXT,
                    atualizado_em TEXT,
                    criado_por TEXT,
                    responsavel TEXT,
                    observacao TEXT,
                    ultimo_login TEXT
                )
                """
            )
    ensure_column("users", "nome", "TEXT")
    ensure_column("users", "senha_hash", "TEXT", "''")
    ensure_column("users", "role", "TEXT", "'usuario'")
    ensure_column("users", "ativo", "INTEGER", "1")
    ensure_column("users", "criado_em", "TEXT")
    ensure_column("users", "atualizado_em", "TEXT")
    ensure_column("users", "criado_por", "TEXT")
    ensure_column("users", "responsavel", "TEXT")
    ensure_column("users", "observacao", "TEXT")
    ensure_column("users", "ultimo_login", "TEXT")


def seed_default_users() -> None:
    legacy_users = load_legacy_auth_users()
    defaults = [
        ("DMLIMA", "admin_geral"),
        ("RAFAEL", "contador"),
    ]
    for username, role in defaults:
        existing = get_user_row(username)
        legacy_password = legacy_users.get(username, "")
        senha_hash = existing.get("senha_hash", "") if existing else ""
        if legacy_password and not senha_hash:
            senha_hash = hash_password(legacy_password)
        if existing:
            execute(
                """
                UPDATE users
                   SET nome=COALESCE(NULLIF(nome,''), ?),
                       senha_hash=COALESCE(NULLIF(?,''), senha_hash),
                       role=?,
                       ativo=1,
                       responsavel=?,
                       atualizado_em=?,
                       criado_por=COALESCE(NULLIF(criado_por,''), ?)
                 WHERE UPPER(username)=UPPER(?)
                """,
                (
                    username,
                    senha_hash,
                    role,
                    username,
                    now_str(),
                    username,
                    username,
                ),
            )
        else:
            upsert_user_record(
                username=username,
                nome=username,
                senha_hash=senha_hash,
                role=role,
                ativo=1,
                criado_por=username,
                responsavel=username,
                observacao="Usuário padrão do sistema.",
            )


def update_user_last_login(username: str) -> None:
    timestamp = now_str()
    execute(
        "UPDATE users SET ultimo_login=?, atualizado_em=? WHERE UPPER(username)=UPPER(?)",
        (timestamp, timestamp, normalize_username(username)),
    )


def set_authenticated_session(username: str, role: str, nome: str) -> None:
    username_norm = normalize_username(username)
    role_norm = user_role_for(username_norm, role)
    nome_final = user_display_name_for(username_norm, nome)
    st.session_state["authenticated"] = True
    st.session_state["is_authenticated"] = True
    st.session_state["auth_user"] = username_norm
    st.session_state["user"] = username_norm
    st.session_state["username"] = username_norm
    st.session_state["user_role"] = role_norm
    st.session_state["user_name"] = nome_final


def clear_authenticated_session_state() -> None:
    for key in [
        "authenticated",
        "is_authenticated",
        "auth_user",
        "user",
        "username",
        "user_role",
        "user_name",
        "page",
        "page_label",
        "session_id",
    ]:
        st.session_state.pop(key, None)


def _auth_cookie_manager():
    if esc is None:
        return None
    try:
        return esc.CookieManager(key="auth_cookie_mgr")
    except Exception:
        return None


def hash_auth_token(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def _auth_now() -> datetime:
    return datetime.now()


def _auth_now_str() -> str:
    return _auth_now().strftime("%Y-%m-%d %H:%M:%S")


def _auth_expiry_str() -> str:
    return (_auth_now() + timedelta(seconds=AUTH_SESSION_TTL_SECONDS)).strftime("%Y-%m-%d %H:%M:%S")


def _auth_cookie_secure_flag() -> bool:
    try:
        headers = getattr(st.context, "headers", None)
        proto = ""
        if headers is not None:
            proto = str(headers.get("X-Forwarded-Proto", "") or headers.get("x-forwarded-proto", "") or "")
        return proto.lower() == "https"
    except Exception:
        return False


def _request_header_value(*names: str) -> str:
    try:
        headers = getattr(st.context, "headers", None)
        if headers is None:
            return ""
        for name in names:
            value = headers.get(name)
            if value:
                return str(value)
    except Exception:
        pass
    return ""


def ensure_auth_sessions_table() -> None:
    if using_postgres():
        execute(
            """
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token_hash TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                last_seen TEXT,
                revoked INTEGER DEFAULT 0,
                user_agent TEXT,
                ip_hint TEXT
            )
            """
        )
    else:
        with get_sqlite_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_hash TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_seen TEXT,
                    revoked INTEGER DEFAULT 0,
                    user_agent TEXT,
                    ip_hint TEXT
                )
                """
            )


def cleanup_expired_auth_sessions() -> None:
    ensure_auth_sessions_table()
    now_txt = _auth_now_str()
    execute(
        """
        DELETE FROM auth_sessions
         WHERE revoked=1 OR expires_at < ?
        """,
        (now_txt,),
    )


def create_auth_session(username: str) -> str:
    ensure_auth_sessions_table()
    cleanup_expired_auth_sessions()
    token = secrets.token_urlsafe(32)
    token_hash = hash_auth_token(token)
    username_norm = normalize_username(username)
    created_at = _auth_now_str()
    expires_at = _auth_expiry_str()
    user_agent = _request_header_value("User-Agent", "user-agent")
    ip_hint = _request_header_value("X-Forwarded-For", "x-forwarded-for", "X-Real-Ip", "x-real-ip")
    execute(
        """
        INSERT INTO auth_sessions (
            token_hash, username, created_at, expires_at, last_seen, revoked, user_agent, ip_hint
        )
        VALUES (?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (token_hash, username_norm, created_at, expires_at, created_at, user_agent, ip_hint),
    )
    return token


def validate_auth_session(token: str) -> str | None:
    if not token:
        return None
    ensure_auth_sessions_table()
    cleanup_expired_auth_sessions()
    token_hash = hash_auth_token(token)
    df = query_df(
        """
        SELECT username, expires_at, revoked
          FROM auth_sessions
         WHERE token_hash=?
         LIMIT 1
        """,
        (token_hash,),
    )
    if df.empty:
        return None
    row = df.iloc[0]
    if int(row.get("revoked", 0) or 0) == 1:
        return None
    expires_at = str(row.get("expires_at") or "").strip()
    if not expires_at or expires_at < _auth_now_str():
        execute("UPDATE auth_sessions SET revoked=1 WHERE token_hash=?", (token_hash,))
        return None
    username = normalize_username(row.get("username", ""))
    execute(
        "UPDATE auth_sessions SET last_seen=? WHERE token_hash=?",
        (_auth_now_str(), token_hash),
    )
    return username or None


def revoke_auth_session(token: str) -> None:
    if not token:
        return
    ensure_auth_sessions_table()
    execute(
        "UPDATE auth_sessions SET revoked=1, last_seen=? WHERE token_hash=?",
        (_auth_now_str(), hash_auth_token(token)),
    )


def _get_auth_token_from_cookie() -> str:
    manager = _auth_cookie_manager()
    if manager is None:
        return ""
    try:
        value = manager.get(AUTH_COOKIE_NAME)
        return str(value or "").strip()
    except Exception:
        return ""


def _get_auth_token_from_query() -> str:
    try:
        return str(st.query_params.get("auth_token", "") or "").strip()
    except Exception:
        return ""


def _set_auth_token_cookie(token: str) -> None:
    manager = _auth_cookie_manager()
    if manager is None:
        return
    try:
        manager.set(
            AUTH_COOKIE_NAME,
            token,
            max_age=AUTH_SESSION_TTL_SECONDS,
            secure=_auth_cookie_secure_flag(),
            same_site="lax",
        )
    except Exception:
        pass


def _delete_auth_token_cookie() -> None:
    manager = _auth_cookie_manager()
    if manager is None:
        return
    try:
        manager.delete(AUTH_COOKIE_NAME)
    except Exception:
        pass


def _delete_query_param_auth_token() -> None:
    try:
        if "auth_token" in st.query_params:
            del st.query_params["auth_token"]
    except Exception:
        pass


def _set_auth_persistence(token: str) -> None:
    _set_auth_token_cookie(token)
    try:
        st.query_params["auth_token"] = token
    except Exception:
        pass


def _restore_persistent_auth_session() -> bool:
    if st.session_state.get("authenticated") or st.session_state.get("is_authenticated"):
        return False
    ensure_auth_sessions_table()
    token = _get_auth_token_from_cookie() or _get_auth_token_from_query()
    if not token:
        return False
    username = validate_auth_session(token)
    if not username:
        _delete_auth_token_cookie()
        _delete_query_param_auth_token()
        return False
    user_row = get_user_row(username)
    legacy_users = configured_users()
    if not user_row and username not in legacy_users:
        revoke_auth_session(token)
        _delete_auth_token_cookie()
        _delete_query_param_auth_token()
        clear_authenticated_session_state()
        return False
    if user_row and int(user_row.get("ativo", 1) or 0) == 0:
        revoke_auth_session(token)
        _delete_auth_token_cookie()
        _delete_query_param_auth_token()
        clear_authenticated_session_state()
        return False
    role = user_row.get("role", "usuario") if user_row else "usuario"
    nome = user_row.get("nome", username) if user_row else username
    set_authenticated_session(username, role, nome)
    update_user_last_login(username)
    requested_page = str(st.query_params.get("page", AUTH_SESSION_DEFAULT_PAGE) or AUTH_SESSION_DEFAULT_PAGE)
    valid_pages = set(NAV_MENU.values()) | {"usuarios"}
    if requested_page not in valid_pages:
        requested_page = AUTH_SESSION_DEFAULT_PAGE
    requested_label = next((label for label, page in NAV_MENU.items() if page == requested_page), AUTH_SESSION_DEFAULT_LABEL)
    st.session_state["page"] = requested_page
    st.session_state["page_label"] = requested_label
    try:
        st.query_params["page"] = requested_page
    except Exception:
        pass
    return True


def _logout_authenticated_session() -> None:
    token = _get_auth_token_from_cookie() or _get_auth_token_from_query()
    if token:
        revoke_auth_session(token)
    _delete_auth_token_cookie()
    _delete_query_param_auth_token()
    clear_authenticated_session_state()


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def current_competencia() -> str:
    today = date.today()
    return f"{today.year}-{today.month:02d}"


def get_setting(key: str, default: str = "") -> str:
    df = query_df("SELECT value FROM settings WHERE key=?", (key,))
    if df.empty:
        return default
    value = df.iloc[0].get("value", default)
    return default if value is None else str(value)


def set_setting(key: str, value: str) -> None:
    execute(
        """
        INSERT INTO settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """,
        (key, str(value)),
    )


def schema_is_current() -> bool:
    if not using_postgres():
        return False
    try:
        return get_setting("schema_version") == SCHEMA_VERSION
    except Exception:
        return False


def active_session_cutoff(minutes: int = 10) -> str:
    return (datetime.now() - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")


def cleanup_active_sessions(minutes: int = 10) -> None:
    execute("DELETE FROM active_sessions WHERE last_seen < ?", (active_session_cutoff(minutes),))


def touch_active_session(page: str = "") -> None:
    if not st.session_state.get("authenticated") and not st.session_state.get("is_authenticated"):
        return
    session_id = str(st.session_state.get("session_id") or "").strip()
    if not session_id:
        session_id = uuid.uuid4().hex
        st.session_state["session_id"] = session_id
    usuario = current_username() or "sistema"
    timestamp = now_str()
    execute(
        """
        INSERT INTO active_sessions (session_id, usuario, page, last_seen, criado_em)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            usuario=excluded.usuario,
            page=excluded.page,
            last_seen=excluded.last_seen
        """,
        (session_id, usuario, str(page or st.session_state.get("page", "")), timestamp, timestamp),
    )
    cleanup_active_sessions()


def current_user() -> str:
    return current_username() or "sistema"


def remove_active_session() -> None:
    session_id = str(st.session_state.get("session_id") or "").strip()
    if session_id:
        execute("DELETE FROM active_sessions WHERE session_id=?", (session_id,))
    st.session_state.pop("session_id", None)


def load_active_sessions() -> pd.DataFrame:
    return query_df(
        """
        SELECT session_id, usuario, COALESCE(page,'') AS page, last_seen, criado_em
          FROM active_sessions
         ORDER BY last_seen DESC
        """
    )


def parse_competencia(competencia: str) -> tuple[int, int]:
    try:
        year_str, month_str = competencia.split("-", 1)
        return int(year_str), int(month_str)
    except Exception:
        today = date.today()
        return today.year, today.month


def get_database_url() -> str:
    try:
        url = st.secrets.get("DATABASE_URL", "")
        if url:
            return str(url)
    except Exception:
        pass
    try:
        secrets_database = st.secrets.get("database", {})
        url = secrets_database.get("url", "") if hasattr(secrets_database, "get") else ""
        if url:
            return str(url)
    except Exception:
        pass
    return os.getenv("DATABASE_URL", "").strip()


def database_url() -> str:
    return get_database_url()


def using_postgres() -> bool:
    url = get_database_url()
    return url.startswith(("postgresql://", "postgres://"))


def db_label() -> str:
    if using_postgres():
        return "PostgreSQL online"
    return str(DB_PATH)


def db_exists() -> bool:
    return True if using_postgres() else DB_PATH.exists()


def get_engine():
    global _ENGINE, _ENGINE_URL
    url = get_database_url()
    engine_url = url or f"sqlite:///{DB_PATH}"
    if _ENGINE is None or _ENGINE_URL != engine_url:
        if url:
            connect_args = {"sslmode": "require"} if url.startswith(("postgresql://", "postgres://")) else {}
            _ENGINE = create_engine(
                url,
                pool_pre_ping=True,
                pool_recycle=300,
                connect_args=connect_args,
            )
        else:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            _ENGINE = create_engine(
                f"sqlite:///{DB_PATH}",
                connect_args={"check_same_thread": False},
            )
        _ENGINE_URL = engine_url
    return _ENGINE


def test_database_connection() -> bool:
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        return result.scalar() == 1


@st.cache_data(ttl=30, show_spinner=False)
def database_status_for_login(database_marker: str) -> tuple[str, str]:
    try:
        total_users = query_df("SELECT COUNT(*) AS total FROM users")
        users_count = int(total_users.iloc[0]["total"] or 0) if not total_users.empty else 0
    except Exception:
        users_count = 0
    try:
        if using_postgres() and test_database_connection():
            return "success", f"Banco: Supabase PostgreSQL conectado | Usuarios: {users_count}"
        if using_postgres():
            return "error", "Banco: Supabase PostgreSQL configurado, mas sem conexao"
        return "warning", f"Banco: SQLite local/temporario | Usuarios: {users_count} | Configure DATABASE_URL nos Secrets"
    except Exception as exc:
        return "error", f"Banco: erro de conexao ({type(exc).__name__})"


def get_sqlite_conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def adapt_sql(sql: str, params: tuple = ()):
    if not using_postgres():
        return sql, params

    adapted = sql.replace(" COLLATE NOCASE", "")
    values: dict[str, object] = {}
    for idx, value in enumerate(params):
        key = f"p{idx}"
        adapted = adapted.replace("?", f":{key}", 1)
        values[key] = value
    return text(adapted), values


def execute(sql: str, params: tuple = ()) -> int:
    adapted_sql, adapted_params = adapt_sql(sql, params)
    if using_postgres():
        with get_engine().begin() as conn:
            result = conn.execute(adapted_sql, adapted_params)
            return max(result.rowcount or 0, 0)
    with get_sqlite_conn() as conn:
        cur = conn.execute(adapted_sql, adapted_params)
        return max(cur.rowcount or 0, 0)


def query_df(sql: str, params: tuple = ()) -> pd.DataFrame:
    adapted_sql, adapted_params = adapt_sql(sql, params)
    if using_postgres():
        with get_engine().connect() as conn:
            return pd.read_sql_query(adapted_sql, conn, params=adapted_params)
    with get_sqlite_conn() as conn:
        return pd.read_sql_query(adapted_sql, conn, params=adapted_params)


def ensure_column(table: str, column: str, coltype: str, default: str = "NULL") -> None:
    if using_postgres():
        exists = query_df(
            """
            SELECT 1
              FROM information_schema.columns
             WHERE table_schema='public'
               AND table_name=?
               AND column_name=?
             LIMIT 1
            """,
            (table, column),
        )
        if exists.empty:
            pg_type = {"INTEGER": "INTEGER", "TEXT": "TEXT", "REAL": "DOUBLE PRECISION"}.get(coltype, coltype)
            execute(f"ALTER TABLE {table} ADD COLUMN {column} {pg_type} DEFAULT {default}")
        return

    with get_sqlite_conn() as conn:
        cols = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype} DEFAULT {default}")


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if using_postgres():
        execute(
            """
            CREATE TABLE IF NOT EXISTS empresas (
                id SERIAL PRIMARY KEY,
                cnpj TEXT NOT NULL UNIQUE,
                razao_social TEXT NOT NULL,
                nome_fantasia TEXT,
                apelido TEXT,
                regime TEXT,
                abertura TEXT,
                situacao TEXT,
                porte TEXT,
                natureza_juridica TEXT,
                capital_social TEXT,
                simples_optante INTEGER DEFAULT 0,
                mei_optante INTEGER DEFAULT 0,
                is_ativo INTEGER DEFAULT 1,
                inativo INTEGER DEFAULT 0,
                criado_em TEXT,
                atualizado_em TEXT
            )
            """
        )
        execute(
            """
            CREATE TABLE IF NOT EXISTS demandas (
                id SERIAL PRIMARY KEY,
                empresa_id INTEGER NOT NULL REFERENCES empresas(id),
                competencia TEXT NOT NULL,
                tipo TEXT NOT NULL,
                feito INTEGER DEFAULT 0,
                criado_em TEXT,
                atualizado_em TEXT,
                observacao TEXT DEFAULT '',
                UNIQUE (empresa_id, competencia, tipo)
            )
            """
        )
        execute(
            """
            CREATE TABLE IF NOT EXISTS empresa_demandas (
                empresa_id INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
                tipo TEXT NOT NULL,
                PRIMARY KEY (empresa_id, tipo)
            )
            """
        )
        execute(
            """
            CREATE TABLE IF NOT EXISTS demanda_tipos (
                id BIGSERIAL PRIMARY KEY,
                codigo INTEGER,
                nome TEXT NOT NULL,
                nome_curto TEXT,
                categoria TEXT,
                ordem INTEGER DEFAULT 999,
                ativo INTEGER DEFAULT 1,
                exige_funcionarios INTEGER DEFAULT 0,
                exige_mei INTEGER DEFAULT 0,
                exige_nao_mei INTEGER DEFAULT 0,
                descricao TEXT,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        execute(
            """
            CREATE TABLE IF NOT EXISTS empresa_demandas_config (
                id BIGSERIAL PRIMARY KEY,
                empresa_id INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
                demanda_tipo_id INTEGER NOT NULL REFERENCES demanda_tipos(id) ON DELETE CASCADE,
                ativo INTEGER DEFAULT 1,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                criado_por TEXT,
                atualizado_por TEXT,
                UNIQUE (empresa_id, demanda_tipo_id)
            )
            """
        )
        execute(
            """
            CREATE TABLE IF NOT EXISTS demanda_status_historico (
                id BIGSERIAL PRIMARY KEY,
                demanda_id INTEGER NOT NULL REFERENCES demandas(id) ON DELETE CASCADE,
                status_anterior TEXT,
                status_novo TEXT,
                observacao TEXT,
                usuario TEXT,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        execute(
            """
            CREATE TABLE IF NOT EXISTS demanda_comentarios (
                id BIGSERIAL PRIMARY KEY,
                demanda_id INTEGER NOT NULL REFERENCES demandas(id) ON DELETE CASCADE,
                comentario TEXT NOT NULL,
                usuario TEXT,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        execute(
            """
            CREATE TABLE IF NOT EXISTS demanda_anexos (
                id BIGSERIAL PRIMARY KEY,
                demanda_id INTEGER NOT NULL REFERENCES demandas(id) ON DELETE CASCADE,
                nome_arquivo TEXT,
                url_arquivo TEXT,
                tipo_arquivo TEXT,
                usuario TEXT,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        execute(
            """
            CREATE TABLE IF NOT EXISTS demanda_ordem_config (
                id BIGSERIAL PRIMARY KEY,
                demanda_tipo_id INTEGER NOT NULL REFERENCES demanda_tipos(id) ON DELETE CASCADE,
                ordem INTEGER NOT NULL,
                atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                atualizado_por TEXT
            )
            """
        )
        execute(
            """
            CREATE TABLE IF NOT EXISTS cliente_compartilhamentos (
                id BIGSERIAL PRIMARY KEY,
                empresa_id INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
                contador_origem TEXT NOT NULL,
                contador_destino TEXT NOT NULL,
                pode_ver INTEGER DEFAULT 1,
                pode_editar INTEGER DEFAULT 0,
                pode_criar_demandas INTEGER DEFAULT 0,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                criado_por TEXT,
                ativo INTEGER DEFAULT 1
            )
            """
        )
        execute(
            """
            CREATE TABLE IF NOT EXISTS cliente_estagiarios (
                id BIGSERIAL PRIMARY KEY,
                empresa_id INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
                contador_responsavel TEXT NOT NULL,
                estagiario_username TEXT NOT NULL,
                pode_ver_cliente INTEGER DEFAULT 1,
                pode_ver_demandas INTEGER DEFAULT 1,
                pode_concluir_demandas INTEGER DEFAULT 1,
                pode_comentar INTEGER DEFAULT 1,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                criado_por TEXT,
                ativo INTEGER DEFAULT 1
            )
            """
        )
        execute(
            """
            CREATE TABLE IF NOT EXISTS demanda_dependencias (
                id BIGSERIAL PRIMARY KEY,
                demanda_tipo_id INTEGER,
                tipo_dependente TEXT NOT NULL,
                depende_de_tipo TEXT NOT NULL,
                obrigatoria INTEGER DEFAULT 1,
                ativo INTEGER DEFAULT 1,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                criado_por TEXT
            )
            """
        )
        execute(
            """
            CREATE TABLE IF NOT EXISTS faturamento_mei (
                id SERIAL PRIMARY KEY,
                empresa_id INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
                competencia TEXT NOT NULL,
                valor DOUBLE PRECISION NOT NULL DEFAULT 0,
                valor_nota_fiscal DOUBLE PRECISION DEFAULT 0,
                valor_mov_extrato DOUBLE PRECISION DEFAULT 0,
                observacao TEXT,
                criado_em TEXT,
                atualizado_em TEXT,
                UNIQUE (empresa_id, competencia)
            )
            """
        )
        execute(
            """
            CREATE TABLE IF NOT EXISTS historico_empresas (
                id SERIAL PRIMARY KEY,
                empresa_id INTEGER NOT NULL REFERENCES empresas(id),
                acao TEXT NOT NULL,
                usuario TEXT NOT NULL,
                resumo TEXT,
                snapshot_anterior TEXT,
                snapshot_atual TEXT,
                criado_em TEXT
            )
            """
        )
        execute(
            """
            CREATE TABLE IF NOT EXISTS historico_regime (
                id SERIAL PRIMARY KEY,
                empresa_id INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
                regime_anterior TEXT,
                regime_novo TEXT NOT NULL,
                vigencia_inicio TEXT NOT NULL,
                registrado_em TEXT NOT NULL,
                origem TEXT
            )
            """
        )
        execute(
            """
            CREATE TABLE IF NOT EXISTS active_sessions (
                session_id TEXT PRIMARY KEY,
                usuario TEXT NOT NULL,
                page TEXT,
                last_seen TEXT,
                criado_em TEXT
            )
            """
        )
        execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        execute(
            """
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token_hash TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                last_seen TEXT,
                revoked INTEGER DEFAULT 0,
                user_agent TEXT,
                ip_hint TEXT
            )
            """
        )
        execute(
            """
            CREATE TABLE IF NOT EXISTS logs_sistema (
                id SERIAL PRIMARY KEY,
                usuario TEXT,
                acao TEXT,
                detalhe TEXT,
                criado_em TEXT
            )
            """
        )
    else:
        with get_sqlite_conn() as conn:
            conn.execute(
            """
            CREATE TABLE IF NOT EXISTS empresas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cnpj TEXT NOT NULL UNIQUE,
                razao_social TEXT NOT NULL,
                nome_fantasia TEXT,
                apelido TEXT,
                regime TEXT,
                abertura TEXT,
                situacao TEXT,
                porte TEXT,
                natureza_juridica TEXT,
                capital_social TEXT,
                simples_optante INTEGER DEFAULT 0,
                mei_optante INTEGER DEFAULT 0,
                is_ativo INTEGER DEFAULT 1,
                inativo INTEGER DEFAULT 0,
                criado_em TEXT,
                atualizado_em TEXT
            )
            """
            )
            conn.execute(
            """
            CREATE TABLE IF NOT EXISTS demandas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                competencia TEXT NOT NULL,
                tipo TEXT NOT NULL,
                feito INTEGER DEFAULT 0,
                criado_em TEXT,
                atualizado_em TEXT,
                observacao TEXT DEFAULT '',
                UNIQUE (empresa_id, competencia, tipo),
                FOREIGN KEY (empresa_id) REFERENCES empresas(id)
            )
            """
            )
            conn.execute(
            """
            CREATE TABLE IF NOT EXISTS empresa_demandas (
                empresa_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                PRIMARY KEY (empresa_id, tipo),
                FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
            )
            """
            )
            conn.execute(
            """
            CREATE TABLE IF NOT EXISTS demanda_tipos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo INTEGER,
                nome TEXT NOT NULL,
                nome_curto TEXT,
                categoria TEXT,
                ordem INTEGER DEFAULT 999,
                ativo INTEGER DEFAULT 1,
                exige_funcionarios INTEGER DEFAULT 0,
                exige_mei INTEGER DEFAULT 0,
                exige_nao_mei INTEGER DEFAULT 0,
                descricao TEXT,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
            )
            conn.execute(
            """
            CREATE TABLE IF NOT EXISTS empresa_demandas_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                demanda_tipo_id INTEGER NOT NULL,
                ativo INTEGER DEFAULT 1,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                criado_por TEXT,
                atualizado_por TEXT,
                UNIQUE (empresa_id, demanda_tipo_id),
                FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE,
                FOREIGN KEY (demanda_tipo_id) REFERENCES demanda_tipos(id) ON DELETE CASCADE
            )
            """
            )
            conn.execute(
            """
            CREATE TABLE IF NOT EXISTS demanda_status_historico (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                demanda_id INTEGER NOT NULL,
                status_anterior TEXT,
                status_novo TEXT,
                observacao TEXT,
                usuario TEXT,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (demanda_id) REFERENCES demandas(id) ON DELETE CASCADE
            )
            """
            )
            conn.execute(
            """
            CREATE TABLE IF NOT EXISTS demanda_comentarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                demanda_id INTEGER NOT NULL,
                comentario TEXT NOT NULL,
                usuario TEXT,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (demanda_id) REFERENCES demandas(id) ON DELETE CASCADE
            )
            """
            )
            conn.execute(
            """
            CREATE TABLE IF NOT EXISTS demanda_anexos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                demanda_id INTEGER NOT NULL,
                nome_arquivo TEXT,
                url_arquivo TEXT,
                tipo_arquivo TEXT,
                usuario TEXT,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (demanda_id) REFERENCES demandas(id) ON DELETE CASCADE
            )
            """
            )
            conn.execute(
            """
            CREATE TABLE IF NOT EXISTS demanda_ordem_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                demanda_tipo_id INTEGER NOT NULL,
                ordem INTEGER NOT NULL,
                atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                atualizado_por TEXT,
                FOREIGN KEY (demanda_tipo_id) REFERENCES demanda_tipos(id) ON DELETE CASCADE
            )
            """
            )
            conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cliente_compartilhamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                contador_origem TEXT NOT NULL,
                contador_destino TEXT NOT NULL,
                pode_ver INTEGER DEFAULT 1,
                pode_editar INTEGER DEFAULT 0,
                pode_criar_demandas INTEGER DEFAULT 0,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                criado_por TEXT,
                ativo INTEGER DEFAULT 1,
                FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
            )
            """
            )
            conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cliente_estagiarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                contador_responsavel TEXT NOT NULL,
                estagiario_username TEXT NOT NULL,
                pode_ver_cliente INTEGER DEFAULT 1,
                pode_ver_demandas INTEGER DEFAULT 1,
                pode_concluir_demandas INTEGER DEFAULT 1,
                pode_comentar INTEGER DEFAULT 1,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                criado_por TEXT,
                ativo INTEGER DEFAULT 1,
                FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
            )
            """
            )
            conn.execute(
            """
            CREATE TABLE IF NOT EXISTS demanda_dependencias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                demanda_tipo_id INTEGER,
                tipo_dependente TEXT NOT NULL,
                depende_de_tipo TEXT NOT NULL,
                obrigatoria INTEGER DEFAULT 1,
                ativo INTEGER DEFAULT 1,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                criado_por TEXT
            )
            """
            )
            conn.execute(
            """
            CREATE TABLE IF NOT EXISTS faturamento_mei (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                competencia TEXT NOT NULL,
                valor REAL NOT NULL DEFAULT 0,
                valor_nota_fiscal REAL DEFAULT 0,
                valor_mov_extrato REAL DEFAULT 0,
                observacao TEXT,
                criado_em TEXT,
                atualizado_em TEXT,
                UNIQUE (empresa_id, competencia),
                FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
            )
            """
            )
            conn.execute(
            """
            CREATE TABLE IF NOT EXISTS historico_empresas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                acao TEXT NOT NULL,
                usuario TEXT NOT NULL,
                resumo TEXT,
                snapshot_anterior TEXT,
                snapshot_atual TEXT,
                criado_em TEXT,
                FOREIGN KEY (empresa_id) REFERENCES empresas(id)
            )
            """
            )
            conn.execute(
            """
            CREATE TABLE IF NOT EXISTS historico_regime (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                regime_anterior TEXT,
                regime_novo TEXT NOT NULL,
                vigencia_inicio TEXT NOT NULL,
                registrado_em TEXT NOT NULL,
                origem TEXT,
                FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
            )
            """
            )
            conn.execute(
            """
            CREATE TABLE IF NOT EXISTS active_sessions (
                session_id TEXT PRIMARY KEY,
                usuario TEXT NOT NULL,
                page TEXT,
                last_seen TEXT,
                criado_em TEXT
            )
            """
            )
            conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
            )
            conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token_hash TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                last_seen TEXT,
                revoked INTEGER DEFAULT 0,
                user_agent TEXT,
                ip_hint TEXT
            )
            """
            )
            conn.execute(
            """
            CREATE TABLE IF NOT EXISTS logs_sistema (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT,
                acao TEXT,
                detalhe TEXT,
                criado_em TEXT
            )
            """
            )
    ensure_column("empresas", "mensalidade", "TEXT")
    ensure_column("empresas", "cidade", "TEXT")
    ensure_column("empresas", "uf", "TEXT")
    ensure_column("empresas", "abertura", "TEXT")
    ensure_column("empresas", "situacao", "TEXT")
    ensure_column("empresas", "porte", "TEXT")
    ensure_column("empresas", "natureza_juridica", "TEXT")
    ensure_column("empresas", "capital_social", "TEXT")
    ensure_column("empresas", "simples_optante", "INTEGER", "0")
    ensure_column("empresas", "mei_optante", "INTEGER", "0")
    ensure_column("empresas", "inativo", "INTEGER", "0")
    ensure_column("empresas", "funcionarios", "INTEGER", "0")
    ensure_column("empresas", "prolabore", "INTEGER", "0")
    ensure_column("empresas", "prefeitura_optante", "INTEGER", "0")
    ensure_column("empresas", "fgts_parc", "INTEGER", "0")
    ensure_column("empresas", "link_rapido", "TEXT")
    ensure_column("empresas", "senhas_acessos", "TEXT")
    ensure_column("empresas", "observacoes", "TEXT")
    ensure_column("empresas", "prefeitura_encerrada_ano_atual", "INTEGER", "0")
    ensure_column("empresas", "prefeitura_quitada_anos", "TEXT")
    ensure_column("empresas", "tem_parcelamento_mensal", "INTEGER", "0")
    ensure_column("empresas", "tem_parcelamento_impostos", "INTEGER", "0")
    ensure_column("empresas", "contador_responsavel", "TEXT", "'DMLIMA'")
    ensure_column("empresas", "criado_por", "TEXT")
    ensure_column("empresas", "compartilhado", "INTEGER", "0")
    ensure_column("demanda_tipos", "codigo", "INTEGER")
    ensure_column("demanda_tipos", "nome", "TEXT")
    ensure_column("demanda_tipos", "nome_curto", "TEXT")
    ensure_column("demanda_tipos", "categoria", "TEXT")
    ensure_column("demanda_tipos", "ordem", "INTEGER", "999")
    ensure_column("demanda_tipos", "ativo", "INTEGER", "1")
    ensure_column("demanda_tipos", "exige_funcionarios", "INTEGER", "0")
    ensure_column("demanda_tipos", "exige_mei", "INTEGER", "0")
    ensure_column("demanda_tipos", "exige_nao_mei", "INTEGER", "0")
    ensure_column("demanda_tipos", "descricao", "TEXT")
    ensure_column("demanda_tipos", "criado_em", "TEXT")
    ensure_column("demanda_tipos", "atualizado_em", "TEXT")
    ensure_column("empresa_demandas_config", "empresa_id", "INTEGER")
    ensure_column("empresa_demandas_config", "demanda_tipo_id", "INTEGER")
    ensure_column("empresa_demandas_config", "ativo", "INTEGER", "1")
    ensure_column("empresa_demandas_config", "criado_em", "TEXT")
    ensure_column("empresa_demandas_config", "atualizado_em", "TEXT")
    ensure_column("empresa_demandas_config", "criado_por", "TEXT")
    ensure_column("empresa_demandas_config", "atualizado_por", "TEXT")
    ensure_column("demandas", "demanda_tipo_id", "INTEGER")
    ensure_column("demandas", "status", "TEXT", "'pendente'")
    ensure_column("demandas", "responsavel", "TEXT")
    ensure_column("demandas", "prioridade", "TEXT", "'normal'")
    ensure_column("demandas", "observacao", "TEXT", "''")
    ensure_column("demandas", "data_limite", "TEXT")
    ensure_column("demandas", "concluida_em", "TEXT")
    ensure_column("demandas", "concluida_por", "TEXT")
    ensure_column("demandas", "criado_por", "TEXT")
    ensure_column("demandas", "atualizado_por", "TEXT")
    ensure_column("demandas", "origem", "TEXT", "'manual'")
    ensure_column("demandas", "replicada_de_id", "INTEGER")
    ensure_column("demandas", "cancelada", "INTEGER", "0")
    ensure_column("demandas", "cancelada_em", "TEXT")
    ensure_column("demandas", "cancelada_por", "TEXT")
    ensure_column("demandas", "motivo_cancelamento", "TEXT")
    ensure_column("demandas", "contador_responsavel", "TEXT")
    ensure_column("demandas", "responsavel_operacional", "TEXT")
    ensure_column("demandas", "liberada", "INTEGER", "1")
    ensure_column("demandas", "bloqueada_por_demanda_id", "INTEGER")
    ensure_column("demandas", "bloqueada_por_tipo", "TEXT")
    ensure_column("demandas", "motivo_bloqueio", "TEXT")
    ensure_column("demandas", "ordem_execucao", "INTEGER", "999")
    ensure_column("cliente_compartilhamentos", "empresa_id", "INTEGER")
    ensure_column("cliente_compartilhamentos", "contador_origem", "TEXT")
    ensure_column("cliente_compartilhamentos", "contador_destino", "TEXT")
    ensure_column("cliente_compartilhamentos", "pode_ver", "INTEGER", "1")
    ensure_column("cliente_compartilhamentos", "pode_editar", "INTEGER", "0")
    ensure_column("cliente_compartilhamentos", "pode_criar_demandas", "INTEGER", "0")
    ensure_column("cliente_compartilhamentos", "criado_em", "TEXT")
    ensure_column("cliente_compartilhamentos", "criado_por", "TEXT")
    ensure_column("cliente_compartilhamentos", "ativo", "INTEGER", "1")
    ensure_column("cliente_estagiarios", "empresa_id", "INTEGER")
    ensure_column("cliente_estagiarios", "contador_responsavel", "TEXT")
    ensure_column("cliente_estagiarios", "estagiario_username", "TEXT")
    ensure_column("cliente_estagiarios", "pode_ver_cliente", "INTEGER", "1")
    ensure_column("cliente_estagiarios", "pode_ver_demandas", "INTEGER", "1")
    ensure_column("cliente_estagiarios", "pode_concluir_demandas", "INTEGER", "1")
    ensure_column("cliente_estagiarios", "pode_comentar", "INTEGER", "1")
    ensure_column("cliente_estagiarios", "criado_em", "TEXT")
    ensure_column("cliente_estagiarios", "criado_por", "TEXT")
    ensure_column("cliente_estagiarios", "ativo", "INTEGER", "1")
    ensure_column("demanda_dependencias", "demanda_tipo_id", "INTEGER")
    ensure_column("demanda_dependencias", "tipo_dependente", "TEXT")
    ensure_column("demanda_dependencias", "depende_de_tipo", "TEXT")
    ensure_column("demanda_dependencias", "obrigatoria", "INTEGER", "1")
    ensure_column("demanda_dependencias", "ativo", "INTEGER", "1")
    ensure_column("demanda_dependencias", "criado_em", "TEXT")
    ensure_column("demanda_dependencias", "criado_por", "TEXT")
    ensure_column("demanda_status_historico", "demanda_id", "INTEGER")
    ensure_column("demanda_status_historico", "status_anterior", "TEXT")
    ensure_column("demanda_status_historico", "status_novo", "TEXT")
    ensure_column("demanda_status_historico", "observacao", "TEXT")
    ensure_column("demanda_status_historico", "usuario", "TEXT")
    ensure_column("demanda_status_historico", "criado_em", "TEXT")
    ensure_column("demanda_comentarios", "demanda_id", "INTEGER")
    ensure_column("demanda_comentarios", "comentario", "TEXT")
    ensure_column("demanda_comentarios", "usuario", "TEXT")
    ensure_column("demanda_comentarios", "criado_em", "TEXT")
    ensure_column("demanda_anexos", "demanda_id", "INTEGER")
    ensure_column("demanda_anexos", "nome_arquivo", "TEXT")
    ensure_column("demanda_anexos", "url_arquivo", "TEXT")
    ensure_column("demanda_anexos", "tipo_arquivo", "TEXT")
    ensure_column("demanda_anexos", "usuario", "TEXT")
    ensure_column("demanda_anexos", "criado_em", "TEXT")
    ensure_column("historico_regime", "cnpj", "TEXT")
    ensure_column("historico_regime", "data_inicio", "TEXT")
    ensure_column("historico_regime", "criado_em", "TEXT")
    ensure_column("historico_regime", "usuario", "TEXT")
    ensure_column("historico_regime", "regime_anterior", "TEXT")
    ensure_column("historico_regime", "origem", "TEXT")
    ensure_user_schema()
    ensure_column("logs_sistema", "usuario", "TEXT")
    ensure_column("logs_sistema", "modulo", "TEXT")
    ensure_column("logs_sistema", "acao", "TEXT")
    ensure_column("logs_sistema", "entidade", "TEXT")
    ensure_column("logs_sistema", "entidade_id", "INTEGER")
    ensure_column("logs_sistema", "detalhe", "TEXT")
    ensure_column("logs_sistema", "criado_em", "TEXT")
    ensure_database_indexes()
    ensure_demanda_tipos_padrao()
    ensure_demanda_dependencias_padrao()
    migrar_responsabilidade_clientes_iniciais()
    migrate_legacy_demandas_schema()
    seed_default_users()


def ensure_database_indexes() -> None:
    index_statements = [
        "CREATE INDEX IF NOT EXISTS idx_empresas_cnpj ON empresas (cnpj)",
        "CREATE INDEX IF NOT EXISTS idx_empresas_razao_social ON empresas (razao_social)",
        "CREATE INDEX IF NOT EXISTS idx_empresas_regime ON empresas (regime)",
        "CREATE INDEX IF NOT EXISTS idx_empresas_is_ativo ON empresas (is_ativo)",
        "CREATE INDEX IF NOT EXISTS idx_empresas_contador_responsavel ON empresas (contador_responsavel)",
        "CREATE INDEX IF NOT EXISTS idx_users_username ON users (username)",
        "CREATE INDEX IF NOT EXISTS idx_demandas_competencia ON demandas (competencia)",
        "CREATE INDEX IF NOT EXISTS idx_demandas_status ON demandas (status)",
        "CREATE INDEX IF NOT EXISTS idx_demandas_responsavel ON demandas (responsavel)",
        "CREATE INDEX IF NOT EXISTS idx_demandas_responsavel_operacional ON demandas (responsavel_operacional)",
        "CREATE INDEX IF NOT EXISTS idx_demandas_contador_responsavel ON demandas (contador_responsavel)",
        "CREATE INDEX IF NOT EXISTS idx_demandas_liberada ON demandas (liberada)",
        "CREATE INDEX IF NOT EXISTS idx_demandas_empresa_id ON demandas (empresa_id)",
        "CREATE INDEX IF NOT EXISTS idx_demandas_tipo ON demandas (tipo)",
        "CREATE INDEX IF NOT EXISTS idx_demandas_empresa_comp_tipo ON demandas (empresa_id, competencia, tipo)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_demanda_tipos_codigo_unique ON demanda_tipos (codigo)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_demanda_tipos_nome_curto_unique ON demanda_tipos (nome_curto)",
        "CREATE INDEX IF NOT EXISTS idx_empresa_demandas_config_empresa_id ON empresa_demandas_config (empresa_id)",
        "CREATE INDEX IF NOT EXISTS idx_empresa_demandas_config_tipo_id ON empresa_demandas_config (demanda_tipo_id)",
        "CREATE INDEX IF NOT EXISTS idx_demanda_status_historico_demanda_id ON demanda_status_historico (demanda_id)",
        "CREATE INDEX IF NOT EXISTS idx_demanda_comentarios_demanda_id ON demanda_comentarios (demanda_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_cliente_compart_unique ON cliente_compartilhamentos (empresa_id, contador_origem, contador_destino)",
        "CREATE INDEX IF NOT EXISTS idx_cliente_compart_destino ON cliente_compartilhamentos (contador_destino)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_cliente_estagiario_unique ON cliente_estagiarios (empresa_id, estagiario_username)",
        "CREATE INDEX IF NOT EXISTS idx_cliente_estagiarios_username ON cliente_estagiarios (estagiario_username)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_demanda_dependencias_unique ON demanda_dependencias (tipo_dependente, depende_de_tipo)",
        "CREATE INDEX IF NOT EXISTS idx_empresa_demandas_empresa_id ON empresa_demandas (empresa_id)",
        "CREATE INDEX IF NOT EXISTS idx_empresa_demandas_tipo ON empresa_demandas (tipo)",
        "CREATE INDEX IF NOT EXISTS idx_faturamento_mei_empresa_id ON faturamento_mei (empresa_id)",
        "CREATE INDEX IF NOT EXISTS idx_faturamento_mei_competencia ON faturamento_mei (competencia)",
        "CREATE INDEX IF NOT EXISTS idx_historico_regime_empresa_id ON historico_regime (empresa_id)",
        "CREATE INDEX IF NOT EXISTS idx_auth_sessions_username ON auth_sessions (username)",
        "CREATE INDEX IF NOT EXISTS idx_active_sessions_usuario ON active_sessions (usuario)",
    ]
    for statement in index_statements:
        execute(statement)


@st.cache_resource(show_spinner=False)
def ensure_database_initialized(database_marker: str) -> bool:
    if schema_is_current():
        return True
    init_db()
    if using_postgres():
        set_setting("schema_version", SCHEMA_VERSION)
    return True


def ensure_database_ready() -> None:
    ensure_database_initialized(f"{get_database_url() or str(DB_PATH)}::{SCHEMA_VERSION}")


def demand_options() -> list[str]:
    return [f"{code} - {label}" for code, label in DEMAND_TYPES]


def option_to_code(option: str) -> str:
    return option.split(" - ", 1)[0].strip()


def show_table(
    df: pd.DataFrame,
    *,
    key: str,
    height: int = 420,
    editable: bool = False,
    column_config: dict | None = None,
    disabled: list[str] | bool = True,
    row_height: int = 30,
    auto_height: bool = False,
    max_height: int = 4000,
) -> pd.DataFrame:
    if auto_height:
        height = calc_empresas_table_height(len(df), row_height=row_height, max_height=max_height)
    return st.data_editor(
        df,
        key=key,
        height=height,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        disabled=disabled if editable else True,
        column_config=column_config,
    )


def calc_empresas_table_height(num_rows: int, *, row_height: int = 35, max_height: int = 4000) -> int:
    header_height = 45
    padding = 20
    min_height = 260
    calc_height = header_height + padding + (max(num_rows, 0) * row_height)
    return max(min_height, min(calc_height, max_height))


def _scroll_key(page_key: str) -> str:
    return f"scroll_{page_key}_y"


def inject_scroll_keeper(page_key: str) -> None:
    storage_key = _scroll_key(page_key)
    components.html(
        f"""
        <script>
        (function() {{
          const storageKey = {json.dumps(storage_key)};
          try {{
            const parentWindow = window.parent;
            if (!parentWindow) return;
            const doc = parentWindow.document;
            const root = doc && doc.documentElement;
            const body = doc && doc.body;
            const saveScroll = function() {{
              try {{
                const y = Math.max(
                  parentWindow.pageYOffset || 0,
                  root ? root.scrollTop : 0,
                  body ? body.scrollTop : 0
                );
                parentWindow.localStorage.setItem(storageKey, String(y));
              }} catch (err) {{}}
            }};
            if (!parentWindow.__ceScrollKeeperBound) {{
              parentWindow.__ceScrollKeeperBound = true;
              parentWindow.addEventListener('scroll', saveScroll, {{ passive: true }});
            }}
            saveScroll();
          }} catch (err) {{}}
        }})();
        </script>
        """,
        height=0,
    )


def mark_restore_scroll(page_key: str) -> None:
    st.session_state[f"restore_scroll_{page_key}"] = True


def restore_scroll_if_needed(page_key: str) -> None:
    flag_key = f"restore_scroll_{page_key}"
    if not st.session_state.pop(flag_key, False):
        return
    storage_key = _scroll_key(page_key)
    components.html(
        f"""
        <script>
        (function() {{
          const storageKey = {json.dumps(storage_key)};
          try {{
            const parentWindow = window.parent;
            if (!parentWindow) return;
            const yRaw = parentWindow.localStorage.getItem(storageKey);
            const y = Number.parseInt(yRaw || '0', 10);
            if (!Number.isFinite(y)) return;
            setTimeout(function() {{
              try {{
                parentWindow.scrollTo(0, y);
                const doc = parentWindow.document;
                if (doc && doc.documentElement) doc.documentElement.scrollTop = y;
                if (doc && doc.body) doc.body.scrollTop = y;
              }} catch (err) {{}}
            }}, 60);
          }} catch (err) {{}}
        }})();
        </script>
        """,
        height=0,
    )


def normalize_cnpj(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) != 14:
        return str(value or "").strip()
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def cnpj_digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def cnpj_biz_url(cnpj_txt: str) -> str:
    cnpj = only_digits(cnpj_txt)
    return f"https://cnpj.biz/{cnpj}" if len(cnpj) == 14 else "https://cnpj.biz/"


def only_digits(value: str) -> str:
    return cnpj_digits(value)


def format_cnpj(value: str) -> str:
    return normalize_cnpj(value)


def cnpj_valido(value: str) -> bool:
    return len(cnpj_digits(value)) == 14


def _normalize_brl_text_for_db(value: str) -> str:
    return format_brl_currency(value)


def split_cidade_uf(value: str) -> tuple[str, str]:
    txt = str(value or "").strip()
    if not txt:
        return "", ""
    if " - " in txt:
        city, uf = txt.rsplit(" - ", 1)
        return city.strip(), uf.strip().upper()
    if "/" in txt:
        city, uf = txt.rsplit("/", 1)
        uf = uf.strip().upper()
        if len(uf) == 2:
            return city.strip(), uf
    return txt, ""


def _first_filled(*values) -> str:
    for value in values:
        if value is None:
            continue
        txt = str(value).strip()
        if txt and txt.lower() not in {"none", "null", "nan"}:
            return txt
    return ""


def _date_br_to_iso(txt: str) -> str:
    value = str(txt or "").strip()
    if not value:
        return ""
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        return value
    parts = value.split("/")
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        dd, mm, yyyy = parts
        if len(yyyy) == 4:
            return f"{yyyy}-{mm.zfill(2)}-{dd.zfill(2)}"
    return value


def _fmt_natureza_juridica(nat_id, nat_desc) -> str:
    desc = str(nat_desc or "").strip()
    raw_id = "".join(ch for ch in str(nat_id or "") if ch.isdigit())
    if raw_id:
        if len(raw_id) >= 4:
            raw_id = f"{raw_id[:-1]}-{raw_id[-1]}"
        if desc:
            return f"{raw_id} - {desc}"
        return raw_id
    return desc


def _guess_apelido(razao: str, fantasia: str) -> str:
    base = _first_filled(fantasia, razao)
    base = str(base or "").strip()
    while base and base[0].isdigit():
        base = base[1:].lstrip(" -./")
    return base.upper()[:28]


def _regime_option(value: str) -> str:
    txt = str(value or "").strip()
    if txt in REGIMES:
        return txt
    if txt.upper().startswith("MEI"):
        return "MEI"
    if txt.upper().startswith("SIMPLES"):
        return "Simples Nacional"
    if txt.upper().startswith("LUCRO PRESUMIDO"):
        return "Lucro Presumido"
    if txt.upper().startswith("LUCRO REAL"):
        return "Lucro Real"
    return REGIMES[0]


def _http_get_text(url: str, timeout: int = 20, accept_json: bool = False) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Accept": "application/json, text/plain, */*" if accept_json else "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _extract_simples_flags_from_cnpjws(payload: dict) -> tuple[int, int]:
    simples = payload.get("simples") or {}
    estabelecimento = payload.get("estabelecimento") or {}
    regimes = estabelecimento.get("regimes_tributarios") or []
    text_blob = " ".join(
        str(item.get("regime_tributario") or item.get("forma_de_tributacao") or "")
        for item in regimes
        if isinstance(item, dict)
    ).upper()

    def truthy(v) -> bool:
        if isinstance(v, bool):
            return v
        return str(v or "").strip().lower() in {"1", "true", "t", "s", "sim", "y", "yes"}

    simples_optante = 0
    mei_optante = 0
    if isinstance(simples, dict):
        simples_optante = 1 if truthy(simples.get("simples") or simples.get("simples_nacional") or simples.get("optante")) else 0
        mei_optante = 1 if truthy(simples.get("mei") or simples.get("simei") or simples.get("simei")) else 0
    if not simples_optante and "SIMPLES" in text_blob:
        simples_optante = 1
    if not mei_optante and ("MEI" in text_blob or "SIMEI" in text_blob):
        mei_optante = 1
    return simples_optante, mei_optante


def _fetch_receitaws_json(cnpj: str) -> dict:
    url = f"https://www.receitaws.com.br/v1/cnpj/{cnpj}"
    text = _http_get_text(url, timeout=20, accept_json=True)
    payload = json.loads(text)
    if isinstance(payload, dict):
        return payload
    raise ValueError("Retorno invalido da ReceitaWS.")


def fetch_empresa_cadastro_on(cnpj_txt: str) -> dict:
    cnpj = only_digits(cnpj_txt)
    if not cnpj_valido(cnpj):
        raise ValueError("Informe um CNPJ v?lido com 14 d?gitos.")

    url_biz = cnpj_biz_url(cnpj)
    try:
        _http_get_text(url_biz, timeout=20, accept_json=False)
    except Exception:
        pass

    info = {
        "source": "cnpj.biz",
        "url": url_biz,
        "cnpj": cnpj,
        "razao_social": "",
        "nome_fantasia": "",
        "apelido": "",
        "regime": "Lucro Presumido",
        "abertura": "",
        "natureza_juridica": "",
        "situacao": "",
        "capital_social": "",
        "cidade": "",
        "uf": "",
        "porte": "",
        "simples_optante": 0,
        "mei_optante": 0,
    }

    cnpjws_payload: dict = {}
    cnpjws_error = None
    try:
        cnpjws_text = _http_get_text(f"https://publica.cnpj.ws/cnpj/{cnpj}", timeout=20, accept_json=True)
        cnpjws_payload = json.loads(cnpjws_text)
        if not isinstance(cnpjws_payload, dict):
            raise ValueError("JSON invalido da cnpj.ws.")
    except Exception as exc:
        cnpjws_error = exc
        cnpjws_payload = {}

    if cnpjws_payload:
        estabelecimento = cnpjws_payload.get("estabelecimento") or {}
        cidade = estabelecimento.get("cidade") or {}
        estado = estabelecimento.get("estado") or {}
        natureza = cnpjws_payload.get("natureza_juridica") or {}
        porte = cnpjws_payload.get("porte") or {}
        simples_optante, mei_optante = _extract_simples_flags_from_cnpjws(cnpjws_payload)

        info["razao_social"] = _first_filled(cnpjws_payload.get("razao_social"), estabelecimento.get("razao_social"))
        info["nome_fantasia"] = _first_filled(estabelecimento.get("nome_fantasia"))
        info["cidade"] = _first_filled(cidade.get("nome"), estabelecimento.get("municipio"), estabelecimento.get("nome_cidade_exterior"))
        info["uf"] = _first_filled(estado.get("sigla"), estabelecimento.get("uf")).upper()
        info["abertura"] = _date_br_to_iso(_first_filled(estabelecimento.get("data_inicio_atividade")))
        info["situacao"] = _first_filled(estabelecimento.get("situacao_cadastral"))
        info["capital_social"] = _first_filled(cnpjws_payload.get("capital_social"))
        info["porte"] = _first_filled(porte.get("descricao"))
        info["natureza_juridica"] = _fmt_natureza_juridica(natureza.get("id"), natureza.get("descricao"))
        info["simples_optante"] = simples_optante
        info["mei_optante"] = mei_optante
        info["regime"] = "MEI" if mei_optante else ("Simples Nacional (ME/EPP)" if simples_optante else "Lucro Presumido")
        info["apelido"] = _guess_apelido(info["razao_social"], info["nome_fantasia"])
        info["source"] = "cnpj.biz + cnpj.ws"
    elif cnpjws_error is not None:
        # If cnpj.ws is unavailable, fall back to ReceitaWS so the user can still proceed.
        try:
            receitaws_payload = _fetch_receitaws_json(cnpj)
        except Exception as exc:
            raise ConnectionError("A consulta online falhou. Tente novamente ou preencha manualmente.") from exc

        info["source"] = "cnpj.biz + receitaws"
        info["razao_social"] = _first_filled(receitaws_payload.get("nome"))
        info["nome_fantasia"] = _first_filled(receitaws_payload.get("fantasia"))
        info["apelido"] = _guess_apelido(info["razao_social"], info["nome_fantasia"])
        info["abertura"] = _date_br_to_iso(_first_filled(receitaws_payload.get("abertura")))
        info["situacao"] = _first_filled(receitaws_payload.get("situacao"))
        info["capital_social"] = _first_filled(receitaws_payload.get("capital_social"))
        info["cidade"] = _first_filled(receitaws_payload.get("municipio"))
        info["uf"] = _first_filled(receitaws_payload.get("uf")).upper()
        info["porte"] = _first_filled(receitaws_payload.get("porte"))
        receitaws_nat = str(receitaws_payload.get("natureza_juridica") or "").strip()
        if receitaws_nat:
            if " - " in receitaws_nat:
                nat_id, nat_desc = receitaws_nat.split(" - ", 1)
            else:
                nat_id, nat_desc = "", receitaws_nat
            info["natureza_juridica"] = _fmt_natureza_juridica(nat_id, nat_desc)
        simples_txt = str(receitaws_payload.get("simples", "") or "").upper()
        simei_txt = str(receitaws_payload.get("simei", "") or "").upper()
        if simples_txt in {"SIM", "S", "TRUE", "1"}:
            info["simples_optante"] = 1
        if simei_txt in {"SIM", "S", "TRUE", "1"}:
            info["mei_optante"] = 1
        info["regime"] = "MEI" if info["mei_optante"] else ("Simples Nacional (ME/EPP)" if info["simples_optante"] else "Lucro Presumido")
        return info

    missing_fields = [
        field for field in ["razao_social", "nome_fantasia", "cidade", "uf", "abertura", "situacao", "capital_social", "porte", "natureza_juridica"]
        if not str(info.get(field, "")).strip()
    ]
    if missing_fields:
        try:
            receitaws_payload = _fetch_receitaws_json(cnpj)
        except Exception:
            receitaws_payload = {}
        if isinstance(receitaws_payload, dict) and receitaws_payload:
            info["source"] = "cnpj.biz + cnpj.ws + receitaws"
            info["razao_social"] = _first_filled(info["razao_social"], receitaws_payload.get("nome"))
            info["nome_fantasia"] = _first_filled(info["nome_fantasia"], receitaws_payload.get("fantasia"))
            info["abertura"] = _first_filled(info["abertura"], _date_br_to_iso(receitaws_payload.get("abertura")))
            info["situacao"] = _first_filled(info["situacao"], receitaws_payload.get("situacao"))
            info["capital_social"] = _first_filled(info["capital_social"], receitaws_payload.get("capital_social"))
            info["cidade"] = _first_filled(info["cidade"], receitaws_payload.get("municipio"))
            info["uf"] = _first_filled(info["uf"], receitaws_payload.get("uf")).upper()
            info["porte"] = _first_filled(info["porte"], receitaws_payload.get("porte"))
            receitaws_nat = str(receitaws_payload.get("natureza_juridica") or "").strip()
            if receitaws_nat and not info["natureza_juridica"]:
                if " - " in receitaws_nat:
                    nat_id, nat_desc = receitaws_nat.split(" - ", 1)
                else:
                    nat_id, nat_desc = "", receitaws_nat
                info["natureza_juridica"] = _fmt_natureza_juridica(nat_id, nat_desc)
            simples_txt = str(receitaws_payload.get("simples", "") or "").upper()
            simei_txt = str(receitaws_payload.get("simei", "") or "").upper()
            if not info["simples_optante"] and simples_txt in {"SIM", "S", "TRUE", "1"}:
                info["simples_optante"] = 1
            if not info["mei_optante"] and simei_txt in {"SIM", "S", "TRUE", "1"}:
                info["mei_optante"] = 1
            info["regime"] = "MEI" if info["mei_optante"] else ("Simples Nacional (ME/EPP)" if info["simples_optante"] else info["regime"])
            info["apelido"] = _guess_apelido(info["razao_social"], info["nome_fantasia"])

    return info


def fetch_empresa_cadastro_on_web(cnpj: str) -> dict:
    return fetch_empresa_cadastro_on(cnpj)


def clean_cell(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def load_empresas(active_only: bool = True, respect_permissions: bool = True) -> pd.DataFrame:
    active_expr = "COALESCE(is_ativo, CASE WHEN COALESCE(inativo,0)=1 THEN 0 ELSE 1 END)"
    where = f"WHERE {active_expr}=1" if active_only else ""
    df = query_df(
        f"""
        SELECT id, cnpj, razao_social, COALESCE(nome_fantasia,'') AS nome_fantasia,
               COALESCE(apelido,'') AS apelido, COALESCE(regime,'') AS regime,
               COALESCE(mensalidade,'') AS mensalidade, COALESCE(cidade,'') AS cidade,
               COALESCE(uf,'') AS uf, COALESCE(inativo,0) AS inativo,
               COALESCE(funcionarios,0) AS funcionarios,
               COALESCE(contador_responsavel,'DMLIMA') AS contador_responsavel,
               COALESCE(criado_por,'') AS criado_por,
               COALESCE(compartilhado,0) AS compartilhado,
               {active_expr} AS is_ativo, atualizado_em
        FROM empresas
        {where}
        ORDER BY razao_social COLLATE NOCASE
        """
    )
    if respect_permissions:
        ids = visible_empresa_ids_for_user()
        if ids is not None:
            if not ids or df.empty:
                return df.iloc[0:0].copy()
            df = df[df["id"].astype(int).isin(ids)].copy()
    return df


def format_brl_currency(val: str) -> str:
    if not val:
        return ""
    clean = str(val).upper().replace("R$", "").replace("$", "").strip()
    if not clean:
        return ""
    try:
        num_chars = []
        for char in clean:
            if char.isdigit() or char in [".", ","]:
                num_chars.append(char)
        num_str = "".join(num_chars)
        if not num_str:
            return clean
            
        if "," in num_str:
            parts = num_str.split(",")
            integer_part = parts[0].replace(".", "")
            decimal_part = parts[1]
            val_float = float(f"{integer_part}.{decimal_part}")
        else:
            if "." in num_str:
                dot_parts = num_str.split(".")
                if len(dot_parts) == 2 and len(dot_parts[1]) != 3:
                    val_float = float(num_str)
                else:
                    val_float = float(num_str.replace(".", ""))
            else:
                val_float = float(num_str)
        
        if val_float.is_integer():
            formatted = f"{int(val_float):,}".replace(",", ".") + " R$"
        else:
            formatted = f"{val_float:,.2f}"
            formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".") + " R$"
        return formatted
    except Exception:
        s = str(val).strip()
        if s and not s.upper().endswith("R$") and not s.upper().endswith("R $"):
            return f"{s} R$"
        return s


def save_empresa(data: dict, empresa_id: int | None = None) -> None:
    if empresa_id and not usuario_pode_editar_cliente(current_username(), int(empresa_id)):
        log_permission_denied("EDITAR_CLIENTE", "empresas", int(empresa_id))
        raise PermissionError("Voce nao tem permissao para editar este cliente.")
    if not empresa_id and is_estagiario() and not _system_context():
        log_permission_denied("CRIAR_CLIENTE", "empresas", 0)
        raise PermissionError("Estagiario nao pode cadastrar cliente.")
    timestamp = now_str()
    before_existing = empresa_row(int(empresa_id)) if empresa_id else {}

    def txt_field(key: str, default: str = "") -> str:
        if key not in data:
            return str(before_existing.get(key, default) or "")
        value = str(data.get(key, "") or "").strip()
        if not value and before_existing.get(key):
            return str(before_existing.get(key, "") or "")
        return value

    def int_field(key: str, default: int = 0) -> int:
        if key not in data:
            return int(before_existing.get(key, default) or 0)
        return int(data.get(key, default) or 0)

    inativo = int_field("inativo", 0)
    is_ativo = 0 if inativo else 1
    simples_optante = int_field("simples_optante", 0)
    mei_optante = int_field("mei_optante", 0)
    requested_contador = normalize_username(txt_field("contador_responsavel", ""))
    if empresa_id:
        contador_responsavel = requested_contador or normalize_username(before_existing.get("contador_responsavel")) or "DMLIMA"
        if not (is_admin_geral() or _system_context()) and contador_responsavel != normalize_username(before_existing.get("contador_responsavel")):
            raise PermissionError("Somente administrador pode trocar o contador responsavel.")
    elif is_admin_geral() or _system_context():
        contador_responsavel = requested_contador or "DMLIMA"
    elif is_contador():
        contador_responsavel = current_username()
    else:
        contador_responsavel = "DMLIMA"
    normalized = {
        "cnpj": normalize_cnpj(txt_field("cnpj")),
        "razao_social": txt_field("razao_social"),
        "nome_fantasia": txt_field("nome_fantasia"),
        "apelido": txt_field("apelido"),
        "regime": txt_field("regime"),
        "abertura": txt_field("abertura"),
        "situacao": txt_field("situacao"),
        "porte": txt_field("porte"),
        "natureza_juridica": txt_field("natureza_juridica"),
        "capital_social": txt_field("capital_social"),
        "simples_optante": simples_optante,
        "mei_optante": mei_optante,
        "mensalidade": format_brl_currency(txt_field("mensalidade")),
        "cidade": txt_field("cidade"),
        "uf": txt_field("uf").upper(),
        "funcionarios": int_field("funcionarios", 0),
        "link_rapido": txt_field("link_rapido"),
        "senhas_acessos": txt_field("senhas_acessos"),
        "observacoes": txt_field("observacoes"),
        "inativo": inativo,
        "is_ativo": is_ativo,
        "contador_responsavel": contador_responsavel,
        "criado_por": normalize_username(txt_field("criado_por", current_username() or contador_responsavel)),
        "compartilhado": int_field("compartilhado", 0),
        "timestamp": timestamp,
    }
    if not normalized["cnpj"] or not normalized["razao_social"]:
        raise ValueError("CNPJ e razao social sao obrigatorios.")
    if empresa_id:
        before = empresa_snapshot(before_existing)
        regime_before = str(before.get("regime", "") or "").strip()
        regime_after = str(normalized["regime"] or "").strip()
        if regime_before and regime_after and regime_before != regime_after and not str(data.get("regime_vigencia", "") or "").strip():
            raise ValueError("Informe a data de vigencia para alterar o regime.")
        execute(
            """
            UPDATE empresas
               SET cnpj=?, razao_social=?, nome_fantasia=?, apelido=?, regime=?,
                   abertura=?, situacao=?, porte=?, natureza_juridica=?, capital_social=?,
                   simples_optante=?, mei_optante=?, mensalidade=?, cidade=?, uf=?,
                   funcionarios=?, link_rapido=?, senhas_acessos=?, observacoes=?,
                   inativo=?, is_ativo=?, contador_responsavel=?, compartilhado=?, atualizado_em=?
             WHERE id=?
            """,
            (
                normalized["cnpj"],
                normalized["razao_social"],
                normalized["nome_fantasia"],
                normalized["apelido"],
                normalized["regime"],
                normalized["abertura"],
                normalized["situacao"],
                normalized["porte"],
                normalized["natureza_juridica"],
                normalized["capital_social"],
                normalized["simples_optante"],
                normalized["mei_optante"],
                normalized["mensalidade"],
                normalized["cidade"],
                normalized["uf"],
                normalized["funcionarios"],
                normalized["link_rapido"],
                normalized["senhas_acessos"],
                normalized["observacoes"],
                normalized["inativo"],
                normalized["is_ativo"],
                normalized["contador_responsavel"],
                normalized["compartilhado"],
                timestamp,
                int(empresa_id),
            ),
        )
        after = empresa_snapshot(empresa_row(int(empresa_id)))
        if before and after and any(str(before.get(key, "")) != str(after.get(key, "")) for key in [
            "cnpj", "razao_social", "nome_fantasia", "apelido", "regime",
            "abertura", "situacao", "porte", "natureza_juridica", "capital_social",
            "simples_optante", "mei_optante", "mensalidade", "cidade", "uf",
            "inativo", "is_ativo",
        ]):
            before_active = int(before.get("is_ativo", 1) or 1)
            after_active = int(after.get("is_ativo", 1) or 1)
            if before_active == 1 and after_active == 0:
                action = "EXCLUSAO"
            elif before_active == 0 and after_active == 1:
                action = "REATIVACAO"
            else:
                action = "ALTERACAO"
            record_empresa_history(int(empresa_id), action, before, after)
        if regime_before and regime_after and regime_before != regime_after:
            record_historico_regime(
                int(empresa_id),
                normalized["cnpj"],
                regime_before,
                regime_after,
                str(data.get("regime_vigencia", "") or "").strip(),
            )
    else:
        execute(
            """
            INSERT INTO empresas
                (cnpj, razao_social, nome_fantasia, apelido, regime, abertura, situacao,
                 porte, natureza_juridica, capital_social, simples_optante, mei_optante,
                 mensalidade, cidade, uf, funcionarios, link_rapido, senhas_acessos, observacoes,
                 inativo, is_ativo, contador_responsavel, criado_por, compartilhado, criado_em, atualizado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized["cnpj"],
                normalized["razao_social"],
                normalized["nome_fantasia"],
                normalized["apelido"],
                normalized["regime"],
                normalized["abertura"],
                normalized["situacao"],
                normalized["porte"],
                normalized["natureza_juridica"],
                normalized["capital_social"],
                normalized["simples_optante"],
                normalized["mei_optante"],
                normalized["mensalidade"],
                normalized["cidade"],
                normalized["uf"],
                normalized["funcionarios"],
                normalized["link_rapido"],
                normalized["senhas_acessos"],
                normalized["observacoes"],
                normalized["inativo"],
                normalized["is_ativo"],
                normalized["contador_responsavel"],
                normalized["criado_por"],
                normalized["compartilhado"],
                timestamp,
                timestamp,
            ),
        )
        created = empresa_snapshot(empresa_row_by_cnpj(normalized["cnpj"]))
        if created:
            record_empresa_history(int(created.get("id", 0) or 0), "INCLUSAO", {}, created)


def empresa_row_by_cnpj(cnpj: str) -> dict:
    df = query_df(
        """
        SELECT id, cnpj, razao_social, COALESCE(nome_fantasia,'') AS nome_fantasia,
               COALESCE(apelido,'') AS apelido, COALESCE(regime,'') AS regime,
               COALESCE(abertura,'') AS abertura, COALESCE(situacao,'') AS situacao,
               COALESCE(porte,'') AS porte, COALESCE(natureza_juridica,'') AS natureza_juridica,
               COALESCE(capital_social,'') AS capital_social,
               COALESCE(simples_optante,0) AS simples_optante,
               COALESCE(mei_optante,0) AS mei_optante,
               COALESCE(mensalidade,'') AS mensalidade, COALESCE(cidade,'') AS cidade,
               COALESCE(uf,'') AS uf, COALESCE(inativo,0) AS inativo,
               COALESCE(funcionarios,0) AS funcionarios,
               COALESCE(link_rapido,'') AS link_rapido,
               COALESCE(senhas_acessos,'') AS senhas_acessos,
               COALESCE(observacoes,'') AS observacoes,
               COALESCE(contador_responsavel,'DMLIMA') AS contador_responsavel,
               COALESCE(criado_por,'') AS criado_por,
               COALESCE(compartilhado,0) AS compartilhado,
               COALESCE(is_ativo, CASE WHEN COALESCE(inativo,0)=1 THEN 0 ELSE 1 END) AS is_ativo,
               atualizado_em, criado_em
          FROM empresas
         WHERE cnpj=?
         ORDER BY id DESC
         LIMIT 1
        """,
        (cnpj,),
    )
    return df.iloc[0].to_dict() if not df.empty else {}






def empresa_row(empresa_id: int) -> dict:
    df = query_df(
        """
        SELECT id, cnpj, razao_social, COALESCE(nome_fantasia,'') AS nome_fantasia,
               COALESCE(apelido,'') AS apelido, COALESCE(regime,'') AS regime,
               COALESCE(abertura,'') AS abertura, COALESCE(situacao,'') AS situacao,
               COALESCE(porte,'') AS porte, COALESCE(natureza_juridica,'') AS natureza_juridica,
               COALESCE(capital_social,'') AS capital_social,
               COALESCE(simples_optante,0) AS simples_optante,
               COALESCE(mei_optante,0) AS mei_optante,
               COALESCE(mensalidade,'') AS mensalidade, COALESCE(cidade,'') AS cidade,
               COALESCE(uf,'') AS uf, COALESCE(inativo,0) AS inativo,
               COALESCE(funcionarios,0) AS funcionarios,
               COALESCE(link_rapido,'') AS link_rapido,
               COALESCE(senhas_acessos,'') AS senhas_acessos,
               COALESCE(observacoes,'') AS observacoes,
               COALESCE(contador_responsavel,'DMLIMA') AS contador_responsavel,
               COALESCE(criado_por,'') AS criado_por,
               COALESCE(compartilhado,0) AS compartilhado,
               COALESCE(is_ativo, CASE WHEN COALESCE(inativo,0)=1 THEN 0 ELSE 1 END) AS is_ativo,
               atualizado_em, criado_em
          FROM empresas
         WHERE id=?
         LIMIT 1
        """,
        (int(empresa_id),),
    )
    return df.iloc[0].to_dict() if not df.empty else {}


def empresa_snapshot(row: dict | None) -> dict:
    if not row:
        return {}
    data = dict(row)
    return {
        "id": int(data.get("id", 0) or 0),
        "cnpj": str(data.get("cnpj", "") or ""),
        "razao_social": str(data.get("razao_social", "") or ""),
        "nome_fantasia": str(data.get("nome_fantasia", "") or ""),
        "apelido": str(data.get("apelido", "") or ""),
        "regime": str(data.get("regime", "") or ""),
        "abertura": str(data.get("abertura", "") or ""),
        "situacao": str(data.get("situacao", "") or ""),
        "porte": str(data.get("porte", "") or ""),
        "natureza_juridica": str(data.get("natureza_juridica", "") or ""),
        "capital_social": str(data.get("capital_social", "") or ""),
        "simples_optante": int(data.get("simples_optante", 0) or 0),
        "mei_optante": int(data.get("mei_optante", 0) or 0),
        "mensalidade": str(data.get("mensalidade", "") or ""),
        "cidade": str(data.get("cidade", "") or ""),
        "uf": str(data.get("uf", "") or ""),
        "funcionarios": int(data.get("funcionarios", 0) or 0),
        "link_rapido": str(data.get("link_rapido", "") or ""),
        "senhas_acessos": str(data.get("senhas_acessos", "") or ""),
        "observacoes": str(data.get("observacoes", "") or ""),
        "contador_responsavel": normalize_username(data.get("contador_responsavel", "DMLIMA")),
        "criado_por": normalize_username(data.get("criado_por", "")),
        "compartilhado": int(data.get("compartilhado", 0) or 0),
        "inativo": int(data.get("inativo", 0) or 0),
        "is_ativo": int(data.get("is_ativo", 1) or 1),
        "atualizado_em": str(data.get("atualizado_em", "") or ""),
        "criado_em": str(data.get("criado_em", "") or ""),
    }


def record_empresa_history(empresa_id: int, action: str, before: dict, after: dict) -> None:
    labels = {
        "cnpj": "CNPJ",
        "razao_social": "Razão social",
        "nome_fantasia": "Nome fantasia",
        "apelido": "Apelido",
        "regime": "Regime",
        "mensalidade": "Mensalidade",
        "cidade": "Cidade",
        "uf": "UF",
        "inativo": "Inativo",
        "is_ativo": "Ativo",
    }
    changed_fields = []
    for key, label in labels.items():
        if str(before.get(key, "")) != str(after.get(key, "")):
            changed_fields.append(label)
    summary = ", ".join(changed_fields) if changed_fields else action
    usuario = str(st.session_state.get("auth_user", "")).strip() or "sistema"
    execute(
        """
        INSERT INTO historico_empresas
            (empresa_id, acao, usuario, resumo, snapshot_anterior, snapshot_atual, criado_em)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(empresa_id),
            action,
            usuario,
            summary,
            json.dumps(before, ensure_ascii=False),
            json.dumps(after, ensure_ascii=False),
            now_str(),
        ),
    )


def record_historico_regime(empresa_id: int, cnpj: str, regime_anterior: str, regime_novo: str, data_inicio: str) -> None:
    usuario = str(st.session_state.get("auth_user", "") or st.session_state.get("user_name", "") or "sistema").strip()
    criado_em = now_str()
    execute(
        """
        INSERT INTO historico_regime
            (empresa_id, cnpj, regime_anterior, regime_novo, vigencia_inicio, data_inicio, registrado_em, criado_em, usuario, origem)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(empresa_id),
            normalize_cnpj(cnpj),
            str(regime_anterior or ""),
            str(regime_novo or ""),
            str(data_inicio or ""),
            str(data_inicio or ""),
            criado_em,
            criado_em,
            usuario,
            "web",
        ),
    )


def load_historico_regime(empresa_id: int) -> pd.DataFrame:
    return query_df(
        """
        SELECT regime_anterior, regime_novo,
               COALESCE(data_inicio, vigencia_inicio, '') AS data_inicio,
               COALESCE(usuario,'') AS usuario,
               COALESCE(criado_em, registrado_em, '') AS criado_em
          FROM historico_regime
         WHERE empresa_id=?
         ORDER BY COALESCE(criado_em, registrado_em, '') DESC, id DESC
        """,
        (int(empresa_id),),
    )


def load_empresa_demandas(empresa_id: int) -> set[str]:
    df = query_df(
        """
        SELECT dt.nome_curto AS tipo
          FROM empresa_demandas_config cfg
          JOIN demanda_tipos dt ON dt.id = cfg.demanda_tipo_id
         WHERE cfg.empresa_id=? AND COALESCE(cfg.ativo,1)=1
         ORDER BY COALESCE(dt.ordem,999), dt.nome
        """,
        (int(empresa_id),),
    )
    if df.empty:
        df = query_df("SELECT tipo FROM empresa_demandas WHERE empresa_id=?", (int(empresa_id),))
    return set(df["tipo"].astype(str).tolist()) if not df.empty else set()


def save_empresa_demandas(empresa_id: int, tipos: list[str]) -> None:
    save_config_demandas_empresa(int(empresa_id), tipos, current_user())
    execute("DELETE FROM empresa_demandas WHERE empresa_id=?", (int(empresa_id),))
    for tipo in sorted(set(tipos)):
        execute(
            "INSERT INTO empresa_demandas (empresa_id, tipo) VALUES (?, ?) ON CONFLICT(empresa_id, tipo) DO NOTHING",
            (int(empresa_id), str(tipo)),
        )


def move_empresa_to_trash(empresa_id: int) -> None:
    row = empresa_row(int(empresa_id))
    if not row:
        raise ValueError("Empresa nao encontrada.")
    payload = {**row, "inativo": 1}
    save_empresa(payload, int(empresa_id))


def restore_empresa_from_trash(empresa_id: int) -> None:
    row = empresa_row(int(empresa_id))
    if not row:
        raise ValueError("Empresa nao encontrada.")
    payload = {**row, "inativo": 0}
    save_empresa(payload, int(empresa_id))


def empresas_export_csv(df: pd.DataFrame) -> bytes:
    export_cols = [
        "id",
        "cnpj",
        "razao_social",
        "nome_fantasia",
        "apelido",
        "regime",
        "contador_responsavel",
        "mensalidade",
        "cidade",
        "uf",
        "inativo",
        "is_ativo",
    ]
    export_df = df.copy()
    for col in export_cols:
        if col not in export_df.columns:
            export_df[col] = ""
    export_df = export_df[export_cols].fillna("")
    return export_df.to_csv(index=False).encode("utf-8-sig")


def empresas_import_dataframe(uploaded_file) -> pd.DataFrame:
    name = str(getattr(uploaded_file, "name", "") or "").lower()
    if name.endswith(".csv") or name.endswith(".txt"):
        df = pd.read_csv(uploaded_file)
    elif name.endswith(".xlsx") or name.endswith(".xls"):
        df = pd.read_excel(uploaded_file)
    else:
        raise ValueError("Formato não suportado. Use CSV ou XLSX.")
    df.columns = [str(col).strip().lower() for col in df.columns]
    return df


def empresas_apply_import(df: pd.DataFrame) -> tuple[int, int]:
    updated = 0
    created = 0
    if df.empty:
        return updated, created

    for _, row in df.iterrows():
        raw_id = row.get("id", "")
        raw_cnpj = row.get("cnpj", "")
        existing = {}
        empresa_id = None

        if pd.notna(raw_id) and str(raw_id).strip():
            try:
                empresa_id = int(float(str(raw_id).replace(",", ".")))
                existing = empresa_row(empresa_id)
            except Exception:
                empresa_id = None

        if not existing and pd.notna(raw_cnpj) and str(raw_cnpj).strip():
            existing = empresa_row_by_cnpj(str(raw_cnpj))
            if existing:
                empresa_id = int(existing.get("id", 0) or 0)

        if not existing and not empresa_id:
            empresa_id = None

        def pick(field: str, default: str = "") -> str:
            value = row.get(field, "")
            if pd.isna(value) or str(value).strip() == "":
                return str(existing.get(field, default) if existing else default)
            return str(value).strip()

        payload = {
            "cnpj": normalize_cnpj(pick("cnpj", existing.get("cnpj", "") if existing else "")),
            "razao_social": pick("razao_social", existing.get("razao_social", "") if existing else "").strip(),
            "nome_fantasia": pick("nome_fantasia", existing.get("nome_fantasia", "") if existing else "").strip(),
            "apelido": pick("apelido", existing.get("apelido", "") if existing else "").strip(),
            "regime": pick("regime", existing.get("regime", "") if existing else "").strip(),
            "mensalidade": pick("mensalidade", existing.get("mensalidade", "") if existing else "").strip(),
            "cidade": pick("cidade", existing.get("cidade", "") if existing else "").strip(),
            "uf": pick("uf", existing.get("uf", "") if existing else "").strip().upper(),
            "contador_responsavel": normalize_username(pick("contador_responsavel", existing.get("contador_responsavel", current_username() or "DMLIMA") if existing else current_username() or "DMLIMA")),
            "inativo": int(float(str(row.get("inativo", existing.get("inativo", 0) if existing else 0) or 0).replace(",", "."))),
        }

        if not payload["cnpj"] or not payload["razao_social"]:
            continue

        if empresa_id and existing:
            save_empresa(payload, empresa_id)
            updated += 1
        else:
            save_empresa(payload, None)
            created += 1

    return updated, created

def load_empresa_history(empresa_id: int) -> pd.DataFrame:
    return query_df(
        """
        SELECT id, empresa_id, acao, usuario, resumo, criado_em,
               snapshot_anterior, snapshot_atual
          FROM historico_empresas
         WHERE empresa_id=?
         ORDER BY id DESC
        """,
        (int(empresa_id),),
    )


def current_role() -> str:
    return current_user_role()


def is_admin() -> bool:
    return is_admin_geral()


def is_estagiario() -> bool:
    return current_user_role() == "estagiario"


def can_manage_demandas() -> bool:
    return is_admin_geral() or is_contador()


def can_config_demandas() -> bool:
    return is_admin_geral() or is_contador()


def can_cancel_demanda(usuario: str | None = None) -> bool:
    usuario_norm = normalize_username(usuario or current_username())
    return usuario_norm in {"DMLIMA", "RAFAEL"} or is_admin_geral() or is_contador()


def can_assign_demanda() -> bool:
    return is_admin_geral() or is_contador()


def _system_context() -> bool:
    return not bool(current_username())


def is_contador_role(role: str) -> bool:
    return str(role or "").strip() in {"admin_geral", "contador"}


def usuario_role(username: str) -> str:
    username_norm = normalize_username(username)
    if username_norm == "DMLIMA":
        return "admin_geral"
    if username_norm == "RAFAEL":
        return "contador"
    row = get_user_row(username_norm)
    return str(row.get("role") or "usuario") if row else "usuario"


def all_contadores() -> list[str]:
    df = get_users_df()
    values = set()
    if not df.empty:
        allowed = df[(df["ativo"] == 1) & (df["role"].isin(["admin_geral", "contador"]))]
        values.update(allowed["username"].astype(str).str.upper().tolist())
    values.update(["DMLIMA", "RAFAEL"])
    return sorted(values)


def all_estagiarios() -> list[str]:
    df = get_users_df()
    if df.empty:
        return []
    allowed = df[(df["ativo"] == 1) & (df["role"].isin(["estagiario", "usuario"]))]
    return sorted(allowed["username"].astype(str).str.upper().tolist())


def visible_empresa_ids_for_user(username: str | None = None, role: str | None = None, *, demandas: bool = False) -> set[int] | None:
    username_norm = normalize_username(username or current_username())
    role = role or (usuario_role(username_norm) if username_norm else current_user_role())
    if not username_norm or role == "admin_geral" or username_norm == "DMLIMA":
        return None

    ids: set[int] = set()
    if role == "contador" or username_norm == "RAFAEL":
        owned = query_df("SELECT id FROM empresas WHERE UPPER(COALESCE(contador_responsavel,''))=UPPER(?)", (username_norm,))
        if not owned.empty:
            ids.update(owned["id"].dropna().astype(int).tolist())
        shared = query_df(
            """
            SELECT empresa_id
              FROM cliente_compartilhamentos
             WHERE UPPER(contador_destino)=UPPER(?)
               AND COALESCE(ativo,1)=1
               AND COALESCE(pode_ver,1)=1
            """,
            (username_norm,),
        )
        if not shared.empty:
            ids.update(shared["empresa_id"].dropna().astype(int).tolist())
        return ids

    est = query_df(
        f"""
        SELECT empresa_id
          FROM cliente_estagiarios
         WHERE UPPER(estagiario_username)=UPPER(?)
           AND COALESCE(ativo,1)=1
           AND COALESCE({'pode_ver_demandas' if demandas else 'pode_ver_cliente'},1)=1
        """,
        (username_norm,),
    )
    if not est.empty:
        ids.update(est["empresa_id"].dropna().astype(int).tolist())
    return ids


def get_clientes_visiveis_para_usuario(username: str | None = None, role: str | None = None) -> pd.DataFrame:
    df = load_empresas(active_only=False, respect_permissions=False)
    ids = visible_empresa_ids_for_user(username, role)
    if ids is None:
        return df
    if not ids or df.empty:
        return df.iloc[0:0].copy()
    return df[df["id"].astype(int).isin(ids)].copy()


def usuario_pode_ver_cliente(username: str | None, empresa_id: int) -> bool:
    ids = visible_empresa_ids_for_user(username)
    return ids is None or int(empresa_id) in ids


def usuario_pode_editar_cliente(username: str | None, empresa_id: int) -> bool:
    username_norm = normalize_username(username or current_username())
    role = usuario_role(username_norm) if username_norm else current_user_role()
    if _system_context() or role == "admin_geral" or username_norm == "DMLIMA":
        return True
    row = empresa_row(int(empresa_id))
    if not row:
        return False
    if (role == "contador" or username_norm == "RAFAEL") and normalize_username(row.get("contador_responsavel")) == username_norm:
        return True
    shared = query_df(
        """
        SELECT 1
          FROM cliente_compartilhamentos
         WHERE empresa_id=?
           AND UPPER(contador_destino)=UPPER(?)
           AND COALESCE(ativo,1)=1
           AND COALESCE(pode_editar,0)=1
         LIMIT 1
        """,
        (int(empresa_id), username_norm),
    )
    return not shared.empty


def usuario_pode_criar_demandas_cliente(username: str | None, empresa_id: int) -> bool:
    username_norm = normalize_username(username or current_username())
    role = usuario_role(username_norm) if username_norm else current_user_role()
    if _system_context() or role == "admin_geral" or username_norm == "DMLIMA":
        return True
    row = empresa_row(int(empresa_id))
    if not row:
        return False
    if (role == "contador" or username_norm == "RAFAEL") and normalize_username(row.get("contador_responsavel")) == username_norm:
        return True
    shared = query_df(
        """
        SELECT 1
          FROM cliente_compartilhamentos
         WHERE empresa_id=?
           AND UPPER(contador_destino)=UPPER(?)
           AND COALESCE(ativo,1)=1
           AND COALESCE(pode_criar_demandas,0)=1
         LIMIT 1
        """,
        (int(empresa_id), username_norm),
    )
    return not shared.empty


def usuario_pode_ver_demanda(username: str | None, demanda_id: int) -> bool:
    row = demanda_row(int(demanda_id))
    if not row:
        return False
    return usuario_pode_ver_cliente(username, int(row.get("empresa_id") or 0))


def usuario_pode_concluir_demanda(username: str | None, demanda_id: int) -> bool:
    username_norm = normalize_username(username or current_username())
    role = usuario_role(username_norm) if username_norm else current_user_role()
    row = demanda_row(int(demanda_id))
    if not row:
        return False
    if _system_context() or role in {"admin_geral", "contador"} or username_norm in {"DMLIMA", "RAFAEL"}:
        return usuario_pode_ver_cliente(username_norm, int(row.get("empresa_id") or 0))
    perm = query_df(
        """
        SELECT 1
          FROM cliente_estagiarios
         WHERE empresa_id=?
           AND UPPER(estagiario_username)=UPPER(?)
           AND COALESCE(ativo,1)=1
           AND COALESCE(pode_ver_demandas,1)=1
           AND COALESCE(pode_concluir_demandas,1)=1
         LIMIT 1
        """,
        (int(row.get("empresa_id") or 0), username_norm),
    )
    return not perm.empty


def can_share_cliente(empresa_id: int, username: str | None = None) -> bool:
    username_norm = normalize_username(username or current_username())
    role = usuario_role(username_norm) if username_norm else current_user_role()
    if _system_context() or role == "admin_geral" or username_norm == "DMLIMA":
        return True
    row = empresa_row(int(empresa_id))
    return bool(row and (role == "contador" or username_norm == "RAFAEL") and normalize_username(row.get("contador_responsavel")) == username_norm)


def log_permission_denied(acao: str, entidade: str, entidade_id: int, detalhe: str = "") -> None:
    try:
        log_action("Permissoes", acao, entidade, entidade_id, current_user(), detalhe)
    except Exception:
        pass


def int_flag(value, default: int = 0) -> int:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except Exception:
        pass
    try:
        return int(value)
    except Exception:
        return default


def get_competencia_atual() -> str:
    return str(st.session_state.get("competencia") or current_competencia())


def normalize_demanda_tipo(tipo: str) -> str:
    value = str(tipo or "").strip()
    if value in DEMAND_LABELS:
        return value
    upper = value.upper()
    for code, label in DEMAND_TYPES:
        if upper == code.upper() or upper == label.upper():
            return code
    return value


def load_demanda_tipos(ativos: bool = True) -> pd.DataFrame:
    where = "WHERE COALESCE(ativo,1)=1" if ativos else ""
    return query_df(
        f"""
        SELECT id, codigo, nome, COALESCE(nome_curto,'') AS nome_curto,
               COALESCE(categoria,'') AS categoria, COALESCE(ordem,999) AS ordem,
               COALESCE(ativo,1) AS ativo,
               COALESCE(exige_funcionarios,0) AS exige_funcionarios,
               COALESCE(exige_mei,0) AS exige_mei,
               COALESCE(exige_nao_mei,0) AS exige_nao_mei,
               COALESCE(descricao,'') AS descricao
          FROM demanda_tipos
          {where}
         ORDER BY COALESCE(ordem,999), COALESCE(codigo,999), nome
        """
    )


def ensure_demanda_tipos_padrao() -> None:
    timestamp = now_str()
    for row in DEMAND_TYPE_ROWS:
        existing = query_df(
            "SELECT id FROM demanda_tipos WHERE codigo=? OR nome_curto=? ORDER BY id LIMIT 1",
            (int(row["codigo"]), str(row["nome_curto"])),
        )
        params = (
            int(row["codigo"]),
            str(row["nome"]),
            str(row["nome_curto"]),
            str(row["categoria"]),
            int(row["ordem"]),
            timestamp,
        )
        if existing.empty:
            execute(
                """
                INSERT INTO demanda_tipos
                    (codigo, nome, nome_curto, categoria, ordem, ativo, criado_em, atualizado_em)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (*params, timestamp),
            )
        else:
            execute(
                """
                UPDATE demanda_tipos
                   SET codigo=?, nome=?, nome_curto=?, categoria=?, ordem=?,
                       ativo=COALESCE(ativo,1), atualizado_em=?
                 WHERE id=?
                """,
                (*params, int(existing.iloc[0]["id"])),
            )


def ensure_demanda_dependencias_padrao() -> None:
    timestamp = now_str()
    for tipo_dependente, depende_de_tipo in DEMANDA_DEPENDENCIAS_PADRAO:
        existing = query_df(
            """
            SELECT id
              FROM demanda_dependencias
             WHERE tipo_dependente=? AND depende_de_tipo=?
             LIMIT 1
            """,
            (tipo_dependente, depende_de_tipo),
        )
        tipo_id = demanda_tipo_id_by_code(tipo_dependente)
        if existing.empty:
            execute(
                """
                INSERT INTO demanda_dependencias
                    (demanda_tipo_id, tipo_dependente, depende_de_tipo, obrigatoria, ativo, criado_em, criado_por)
                VALUES (?, ?, ?, 1, 1, ?, ?)
                """,
                (int(tipo_id or 0) or None, tipo_dependente, depende_de_tipo, timestamp, "sistema"),
            )
        else:
            execute(
                """
                UPDATE demanda_dependencias
                   SET demanda_tipo_id=?, obrigatoria=1, ativo=COALESCE(ativo,1)
                 WHERE id=?
                """,
                (int(tipo_id or 0) or None, int(existing.iloc[0]["id"])),
            )


def migrar_responsabilidade_clientes_iniciais() -> dict:
    report = {"clientes_atualizados": 0, "demandas_atualizadas": 0, "clientes_ignorados": 0, "erros": []}
    try:
        report["clientes_atualizados"] = execute(
            """
            UPDATE empresas
               SET contador_responsavel='DMLIMA',
                   criado_por=COALESCE(NULLIF(criado_por,''), 'DMLIMA')
             WHERE contador_responsavel IS NULL OR TRIM(contador_responsavel)=''
            """
        )
        report["clientes_ignorados"] = int(query_df("SELECT COUNT(*) AS total FROM empresas WHERE COALESCE(contador_responsavel,'')<>''").iloc[0]["total"])
        report["demandas_atualizadas"] = execute(
            """
            UPDATE demandas
               SET contador_responsavel = (
                   SELECT COALESCE(NULLIF(e.contador_responsavel,''), 'DMLIMA')
                     FROM empresas e
                    WHERE e.id = demandas.empresa_id
                    LIMIT 1
               )
             WHERE contador_responsavel IS NULL OR TRIM(contador_responsavel)=''
            """
        )
    except Exception as exc:
        report["erros"].append(str(exc))
    return report


def migrate_legacy_demandas_schema() -> None:
    execute(
        """
        UPDATE demandas
           SET status = CASE WHEN COALESCE(feito,0)=1 THEN 'concluida' ELSE 'pendente' END
         WHERE status IS NULL OR status=''
        """
    )
    execute(
        """
        UPDATE demandas
           SET prioridade = 'normal'
         WHERE prioridade IS NULL OR prioridade=''
        """
    )
    execute(
        """
        UPDATE demandas
           SET origem = 'manual'
         WHERE origem IS NULL OR origem=''
        """
    )
    execute(
        """
        UPDATE demandas
           SET concluida_em = atualizado_em
         WHERE status='concluida' AND (concluida_em IS NULL OR concluida_em='')
        """
    )
    execute(
        """
        UPDATE demandas
           SET demanda_tipo_id = (SELECT dt.id FROM demanda_tipos dt WHERE dt.nome_curto = demandas.tipo LIMIT 1)
         WHERE demanda_tipo_id IS NULL
        """
    )
    execute(
        """
        UPDATE demandas
           SET contador_responsavel = (
               SELECT COALESCE(NULLIF(e.contador_responsavel,''), 'DMLIMA')
                 FROM empresas e
                WHERE e.id = demandas.empresa_id
                LIMIT 1
           )
         WHERE contador_responsavel IS NULL OR TRIM(contador_responsavel)=''
        """
    )
    execute(
        """
        UPDATE demandas
           SET responsavel_operacional = COALESCE(NULLIF(responsavel_operacional,''), responsavel)
         WHERE responsavel IS NOT NULL AND responsavel<>''
        """
    )
    execute(
        """
        UPDATE demandas
           SET ordem_execucao = COALESCE(
               (SELECT dt.ordem FROM demanda_tipos dt WHERE dt.nome_curto = demandas.tipo LIMIT 1),
               999
           )
         WHERE ordem_execucao IS NULL OR ordem_execucao=999
        """
    )
    execute(
        """
        INSERT INTO empresa_demandas_config
            (empresa_id, demanda_tipo_id, ativo, criado_em, atualizado_em, criado_por, atualizado_por)
        SELECT ed.empresa_id, dt.id, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'migracao', 'migracao'
          FROM empresa_demandas ed
          JOIN demanda_tipos dt ON dt.nome_curto = ed.tipo
        ON CONFLICT(empresa_id, demanda_tipo_id) DO NOTHING
        """
    )


def demanda_tipo_id_by_code(tipo: str) -> int | None:
    code = normalize_demanda_tipo(tipo)
    df = query_df("SELECT id FROM demanda_tipos WHERE nome_curto=? OR nome=? LIMIT 1", (code, code))
    if df.empty:
        ensure_demanda_tipos_padrao()
        df = query_df("SELECT id FROM demanda_tipos WHERE nome_curto=? OR nome=? LIMIT 1", (code, code))
    return int(df.iloc[0]["id"]) if not df.empty else None


def load_empresas_ativas() -> pd.DataFrame:
    active_expr = "COALESCE(is_ativo, CASE WHEN COALESCE(inativo,0)=1 THEN 0 ELSE 1 END)"
    df = query_df(
        f"""
        SELECT id, cnpj, razao_social, COALESCE(nome_fantasia,'') AS nome_fantasia,
               COALESCE(apelido,'') AS apelido, COALESCE(regime,'') AS regime,
               COALESCE(cidade,'') AS cidade, COALESCE(uf,'') AS uf,
               COALESCE(funcionarios,0) AS funcionarios,
               COALESCE(contador_responsavel,'DMLIMA') AS contador_responsavel,
               COALESCE(criado_por,'') AS criado_por,
               COALESCE(compartilhado,0) AS compartilhado,
               COALESCE(prefeitura_encerrada_ano_atual,0) AS prefeitura_encerrada_ano_atual,
               COALESCE(prefeitura_quitada_anos,'') AS prefeitura_quitada_anos,
               COALESCE(tem_parcelamento_mensal,0) AS tem_parcelamento_mensal,
               COALESCE(tem_parcelamento_impostos,0) AS tem_parcelamento_impostos,
               {active_expr} AS is_ativo
          FROM empresas
         WHERE {active_expr}=1
        ORDER BY COALESCE(apelido,''), razao_social COLLATE NOCASE
        """
    )
    ids = visible_empresa_ids_for_user(demandas=True)
    if ids is not None:
        if not ids or df.empty:
            return df.iloc[0:0].copy()
        df = df[df["id"].astype(int).isin(ids)].copy()
    return df


def load_demandas(competencia: str, filtros: dict | None = None) -> pd.DataFrame:
    df = query_df(
        """
        SELECT d.id AS demanda_id, d.id, d.empresa_id, d.demanda_tipo_id, d.competencia, d.tipo,
               COALESCE(dt.nome, d.tipo) AS demanda,
               COALESCE(d.status, CASE WHEN COALESCE(d.feito,0)=1 THEN 'concluida' ELSE 'pendente' END) AS status,
               CASE WHEN COALESCE(d.status,'')='concluida' OR COALESCE(d.feito,0)=1 THEN 1 ELSE 0 END AS feito,
               COALESCE(d.contador_responsavel, e.contador_responsavel, 'DMLIMA') AS contador_responsavel,
               COALESCE(d.responsavel_operacional, d.responsavel, '') AS responsavel_operacional,
               COALESCE(d.responsavel, d.responsavel_operacional, '') AS responsavel,
               COALESCE(d.prioridade,'normal') AS prioridade,
               COALESCE(d.observacao,'') AS observacao,
               COALESCE(d.data_limite,'') AS data_limite,
               COALESCE(d.atualizado_em,'') AS atualizado_em,
               COALESCE(d.concluida_em,'') AS concluida_em,
               COALESCE(d.concluida_por,'') AS concluida_por,
               COALESCE(d.criado_em,'') AS criado_em,
               COALESCE(d.criado_por,'') AS criado_por,
               COALESCE(d.atualizado_por,'') AS atualizado_por,
               COALESCE(d.origem,'manual') AS origem,
               COALESCE(d.replicada_de_id,0) AS replicada_de_id,
               COALESCE(d.cancelada,0) AS cancelada,
               COALESCE(d.liberada,1) AS liberada,
               COALESCE(d.bloqueada_por_demanda_id,0) AS bloqueada_por_demanda_id,
               COALESCE(d.bloqueada_por_tipo,'') AS bloqueada_por_tipo,
               COALESCE(d.motivo_bloqueio,'') AS motivo_bloqueio,
               COALESCE(d.ordem_execucao,999) AS ordem_execucao,
               e.razao_social, e.cnpj, COALESCE(e.apelido,'') AS apelido,
               COALESCE(e.regime,'') AS regime, COALESCE(e.cidade,'') AS cidade,
               COALESCE(e.uf,'') AS uf, COALESCE(e.funcionarios,0) AS funcionarios,
               COALESCE(dt.ordem,999) AS ordem_tipo
          FROM demandas d
          JOIN empresas e ON e.id = d.empresa_id
          LEFT JOIN demanda_tipos dt ON dt.id = d.demanda_tipo_id OR dt.nome_curto = d.tipo
         WHERE d.competencia=?
         ORDER BY COALESCE(dt.ordem,999), COALESCE(e.apelido,''), e.razao_social COLLATE NOCASE
        """,
        (competencia,),
    )
    if df.empty:
        return df

    ids = visible_empresa_ids_for_user(demandas=True)
    if ids is not None:
        if not ids:
            return df.iloc[0:0].copy()
        df = df[df["empresa_id"].astype(int).isin(ids)].copy()
        if is_estagiario() and current_username():
            username = current_username()
            assigned = df["responsavel_operacional"].astype(str).str.upper() == username
            unassigned_allowed = df["responsavel_operacional"].fillna("").astype(str).str.strip() == ""
            df = df[assigned | unassigned_allowed].copy()

    df["tipo"] = df["tipo"].map(normalize_demanda_tipo)
    df["demanda"] = df.apply(lambda row: row["demanda"] or DEMAND_LABELS.get(row["tipo"], row["tipo"]), axis=1)
    df["status_label"] = df["status"].map(lambda s: DEMANDA_STATUS_LABELS.get(str(s), str(s)))
    df["liberacao"] = df["liberada"].map(lambda v: "Liberada" if int(v or 0) == 1 else "Bloqueada")
    df["bloqueio"] = df["motivo_bloqueio"].fillna("")
    df["empresa"] = df.apply(
        lambda row: str(row.get("apelido") or row.get("razao_social") or "").strip(),
        axis=1,
    )
    today = date.today().isoformat()
    df["atrasada"] = df.apply(
        lambda row: bool(str(row.get("data_limite") or "").strip() and str(row.get("data_limite")) < today and str(row.get("status")) not in {"concluida", "dispensada", "cancelada"}),
        axis=1,
    )

    filtros = filtros or {}
    search = str(filtros.get("busca", "") or "").strip().upper()
    if search:
        blob = (
            df["empresa"].fillna("")
            + " "
            + df["razao_social"].fillna("")
            + " "
            + df["cnpj"].fillna("")
            + " "
            + df["tipo"].fillna("")
        ).str.upper()
        df = df[blob.str.contains(search, regex=False)]
    for key, col in [
        ("tipo", "tipo"),
        ("status", "status"),
        ("responsavel", "responsavel_operacional"),
        ("contador_responsavel", "contador_responsavel"),
        ("prioridade", "prioridade"),
        ("regime", "regime"),
        ("liberada", "liberacao"),
    ]:
        value = str(filtros.get(key, "") or "").strip()
        if value and value != "Todos":
            df = df[df[col].fillna("").astype(str) == value]
    if filtros.get("minhas"):
        df = df[
            (df["responsavel_operacional"].astype(str).str.upper() == current_username())
            | (df["responsavel"].astype(str).str.upper() == current_username())
        ]
    if filtros.get("atrasadas"):
        df = df[df["atrasada"]]
    if not filtros.get("mostrar_concluidas", True):
        df = df[~df["status"].isin(["concluida", "dispensada", "cancelada"])]
    return df.copy()


def log_action(modulo: str, acao: str, entidade: str = "", entidade_id: int | None = None, usuario: str | None = None, detalhe: str = "") -> None:
    execute(
        """
        INSERT INTO logs_sistema (modulo, acao, entidade, entidade_id, usuario, detalhe, criado_em)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (modulo, acao, entidade, int(entidade_id or 0), usuario or current_user(), detalhe, now_str()),
    )


def create_demanda(
    empresa_id: int,
    tipo: str,
    competencia: str,
    origem: str = "manual",
    responsavel: str | None = None,
    prioridade: str = "normal",
    observacao: str = "",
    data_limite: str = "",
    replicada_de_id: int | None = None,
) -> int:
    if not usuario_pode_criar_demandas_cliente(current_username(), int(empresa_id)):
        log_permission_denied("CRIAR_DEMANDA", "empresas", int(empresa_id))
        raise PermissionError("Voce nao tem permissao para criar demandas deste cliente.")
    empresa = empresa_row(int(empresa_id))
    contador_resp = normalize_username(empresa.get("contador_responsavel", "DMLIMA")) or "DMLIMA"
    tipo_code = normalize_demanda_tipo(tipo)
    tipo_id = demanda_tipo_id_by_code(tipo_code)
    timestamp = now_str()
    ordem_execucao = demand_order_value(tipo_code)
    created = execute(
        """
        INSERT INTO demandas
            (empresa_id, demanda_tipo_id, tipo, competencia, status, feito, contador_responsavel, responsavel,
             responsavel_operacional,
             prioridade, observacao, data_limite, criado_em, atualizado_em, criado_por,
             atualizado_por, origem, replicada_de_id, cancelada, liberada, ordem_execucao)
        VALUES (?, ?, ?, ?, 'pendente', 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1, ?)
        ON CONFLICT(empresa_id, competencia, tipo) DO NOTHING
        """,
        (
            int(empresa_id),
            int(tipo_id or 0) or None,
            tipo_code,
            competencia,
            contador_resp,
            str(responsavel or "").strip(),
            str(responsavel or "").strip(),
            prioridade if prioridade in DEMANDA_PRIORIDADES else "normal",
            str(observacao or "").strip(),
            str(data_limite or "").strip(),
            timestamp,
            timestamp,
            current_user(),
            current_user(),
            str(origem or "manual"),
            int(replicada_de_id) if replicada_de_id else None,
            ordem_execucao,
        ),
    )
    if created:
        log_action("Demandas", "CRIAR", "demandas", 0, current_user(), f"{empresa_id} {competencia} {tipo_code}")
        recalcular_liberacao_demandas(int(empresa_id), competencia)
    return created


def create_demandas(competencia: str, tipo: str, empresa_ids: list[int]) -> int:
    created = 0
    for empresa_id in empresa_ids:
        created += create_demanda(int(empresa_id), tipo, competencia, "manual")
    return created


def demanda_row(demanda_id: int) -> dict:
    df = query_df(
        """
        SELECT d.*, COALESCE(dt.nome,d.tipo) AS demanda, e.razao_social, e.cnpj,
               COALESCE(e.apelido,'') AS apelido, COALESCE(e.regime,'') AS regime,
               COALESCE(e.contador_responsavel,'DMLIMA') AS empresa_contador_responsavel
          FROM demandas d
          JOIN empresas e ON e.id=d.empresa_id
          LEFT JOIN demanda_tipos dt ON dt.id=d.demanda_tipo_id OR dt.nome_curto=d.tipo
         WHERE d.id=?
         LIMIT 1
        """,
        (int(demanda_id),),
    )
    return df.iloc[0].to_dict() if not df.empty else {}


def load_demanda_dependencias(ativos: bool = True) -> pd.DataFrame:
    where = "WHERE COALESCE(ativo,1)=1" if ativos else ""
    return query_df(
        f"""
        SELECT id, demanda_tipo_id, tipo_dependente, depende_de_tipo,
               COALESCE(obrigatoria,1) AS obrigatoria,
               COALESCE(ativo,1) AS ativo
          FROM demanda_dependencias
          {where}
         ORDER BY tipo_dependente, depende_de_tipo
        """
    )


def recalcular_liberacao_demandas(empresa_id: int, competencia: str) -> None:
    deps = load_demanda_dependencias(True)
    if deps.empty:
        return
    demandas_empresa = query_df(
        """
        SELECT id, tipo, COALESCE(status,'pendente') AS status
          FROM demandas
         WHERE empresa_id=? AND competencia=? AND COALESCE(cancelada,0)=0
        """,
        (int(empresa_id), competencia),
    )
    if demandas_empresa.empty:
        return
    by_tipo = {str(row["tipo"]): row.to_dict() for _, row in demandas_empresa.iterrows()}
    for _, dep in deps.iterrows():
        dependente = normalize_demanda_tipo(str(dep["tipo_dependente"]))
        requisito = normalize_demanda_tipo(str(dep["depende_de_tipo"]))
        if dependente not in by_tipo:
            continue
        dependente_row = by_tipo[dependente]
        requisito_row = by_tipo.get(requisito)
        if not requisito_row:
            continue
        requisito_concluido = str(requisito_row.get("status") or "") == "concluida"
        if requisito_concluido:
            execute(
                """
                UPDATE demandas
                   SET liberada=1, bloqueada_por_demanda_id=NULL, bloqueada_por_tipo=NULL,
                       motivo_bloqueio=NULL, atualizado_em=?
                 WHERE id=?
                """,
                (now_str(), int(dependente_row["id"])),
            )
        elif str(dependente_row.get("status") or "") != "concluida":
            execute(
                """
                UPDATE demandas
                   SET liberada=0, bloqueada_por_demanda_id=?, bloqueada_por_tipo=?,
                       motivo_bloqueio=?, atualizado_em=?
                 WHERE id=?
                """,
                (
                    int(requisito_row["id"]),
                    requisito,
                    f"Aguardando conclusao de: {DEMAND_LABELS.get(requisito, requisito)}",
                    now_str(),
                    int(dependente_row["id"]),
                ),
            )


def record_demanda_status(demanda_id: int, status_anterior: str, status_novo: str, usuario: str, observacao: str = "") -> None:
    execute(
        """
        INSERT INTO demanda_status_historico
            (demanda_id, status_anterior, status_novo, observacao, usuario, criado_em)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (int(demanda_id), status_anterior, status_novo, observacao, usuario, now_str()),
    )


def update_demanda_status(demanda_id: int, status_novo, usuario: str | None = None, observacao: str | None = None) -> None:
    usuario = usuario or current_user()
    if isinstance(status_novo, bool):
        status_novo = "concluida" if status_novo else "pendente"
    status_novo = str(status_novo or "pendente").strip()
    if status_novo not in DEMANDA_STATUS:
        raise ValueError("Status invalido.")
    before = demanda_row(int(demanda_id))
    if not before:
        raise ValueError("Demanda nao encontrada.")
    if not usuario_pode_ver_demanda(usuario, int(demanda_id)):
        log_permission_denied("ALTERAR_DEMANDA", "demandas", int(demanda_id))
        raise PermissionError("Voce nao tem permissao para alterar esta demanda.")
    if status_novo == "concluida":
        if not usuario_pode_concluir_demanda(usuario, int(demanda_id)):
            log_permission_denied("CONCLUIR_DEMANDA", "demandas", int(demanda_id))
            raise PermissionError("Voce nao tem permissao para concluir esta demanda.")
        if int_flag(before.get("liberada"), 1) != 1:
            raise PermissionError(str(before.get("motivo_bloqueio") or "Demanda bloqueada por dependencia."))
    status_anterior = str(before.get("status") or ("concluida" if int(before.get("feito", 0) or 0) else "pendente"))
    timestamp = now_str()
    concluida_em = timestamp if status_novo == "concluida" else (before.get("concluida_em") or "")
    concluida_por = usuario if status_novo == "concluida" else (before.get("concluida_por") or "")
    feito = 1 if status_novo == "concluida" else 0
    execute(
        """
        UPDATE demandas
           SET status=?, feito=?, observacao=COALESCE(?, observacao),
               concluida_em=?, concluida_por=?, atualizado_em=?, atualizado_por=?,
               cancelada=CASE WHEN ?='cancelada' THEN 1 ELSE COALESCE(cancelada,0) END
         WHERE id=?
        """,
        (status_novo, feito, observacao, concluida_em, concluida_por, timestamp, usuario, status_novo, int(demanda_id)),
    )
    if status_anterior != status_novo:
        record_demanda_status(int(demanda_id), status_anterior, status_novo, usuario, observacao or "")
    log_action("Demandas", "STATUS", "demandas", int(demanda_id), usuario, f"{status_anterior} -> {status_novo}")
    recalcular_liberacao_demandas(int(before.get("empresa_id") or 0), str(before.get("competencia") or ""))


def update_demanda_observacao(demanda_id: int, observacao: str, usuario: str | None = None) -> None:
    execute(
        "UPDATE demandas SET observacao=?, atualizado_em=?, atualizado_por=? WHERE id=?",
        (str(observacao or ""), now_str(), usuario or current_user(), int(demanda_id)),
    )


def update_demanda_responsavel(demanda_id: int, responsavel: str, usuario: str | None = None) -> None:
    execute(
        "UPDATE demandas SET responsavel=?, atualizado_em=?, atualizado_por=? WHERE id=?",
        (str(responsavel or "").strip(), now_str(), usuario or current_user(), int(demanda_id)),
    )


def update_demanda_prioridade(demanda_id: int, prioridade: str, usuario: str | None = None) -> None:
    prioridade = prioridade if prioridade in DEMANDA_PRIORIDADES else "normal"
    execute(
        "UPDATE demandas SET prioridade=?, atualizado_em=?, atualizado_por=? WHERE id=?",
        (prioridade, now_str(), usuario or current_user(), int(demanda_id)),
    )


def update_demanda_campos(
    demanda_id: int,
    *,
    responsavel: str,
    prioridade: str,
    data_limite: str,
    observacao: str,
    usuario: str | None = None,
) -> None:
    usuario = usuario or current_user()
    if not usuario_pode_ver_demanda(usuario, int(demanda_id)):
        log_permission_denied("EDITAR_DEMANDA", "demandas", int(demanda_id))
        raise PermissionError("Voce nao tem permissao para editar esta demanda.")
    execute(
        """
        UPDATE demandas
           SET responsavel=?, responsavel_operacional=?, prioridade=?, data_limite=?, observacao=?,
               atualizado_em=?, atualizado_por=?
         WHERE id=?
        """,
        (
            str(responsavel or "").strip(),
            str(responsavel or "").strip(),
            prioridade if prioridade in DEMANDA_PRIORIDADES else "normal",
            str(data_limite or "").strip(),
            str(observacao or "").strip(),
            now_str(),
            usuario,
            int(demanda_id),
        ),
    )


def delete_or_cancel_demanda(demanda_id: int, usuario: str | None = None, motivo: str = "") -> None:
    if not can_cancel_demanda(usuario):
        raise PermissionError("Seu perfil nao permite cancelar demandas.")
    usuario = usuario or current_user()
    if not usuario_pode_ver_demanda(usuario, int(demanda_id)):
        log_permission_denied("CANCELAR_DEMANDA", "demandas", int(demanda_id))
        raise PermissionError("Voce nao tem permissao para cancelar esta demanda.")
    update_demanda_status(int(demanda_id), "cancelada", usuario, motivo)
    execute(
        """
        UPDATE demandas
           SET cancelada=1, cancelada_em=?, cancelada_por=?, motivo_cancelamento=?
         WHERE id=?
        """,
        (now_str(), usuario, str(motivo or "").strip(), int(demanda_id)),
    )


def delete_demanda(demanda_id: int) -> None:
    delete_or_cancel_demanda(int(demanda_id), current_user(), "Cancelada pela interface web.")


def concluir_demanda(demanda_id: int, usuario: str | None = None) -> None:
    update_demanda_status(int(demanda_id), "concluida", usuario or current_user())


def reabrir_demanda(demanda_id: int, usuario: str | None = None) -> None:
    usuario = usuario or current_user()
    before = demanda_row(int(demanda_id))
    if not before:
        raise ValueError("Demanda nao encontrada.")
    if not usuario_pode_concluir_demanda(usuario, int(demanda_id)):
        log_permission_denied("REABRIR_DEMANDA", "demandas", int(demanda_id))
        raise PermissionError("Voce nao tem permissao para reabrir esta demanda.")
    status_anterior = str(before.get("status") or "concluida")
    execute(
        """
        UPDATE demandas
           SET status='pendente', feito=0, concluida_em=NULL, concluida_por=NULL,
               cancelada=0, atualizado_em=?, atualizado_por=?
         WHERE id=?
        """,
        (now_str(), usuario, int(demanda_id)),
    )
    record_demanda_status(int(demanda_id), status_anterior, "pendente", usuario, "Reaberta")
    recalcular_liberacao_demandas(int(before.get("empresa_id") or 0), str(before.get("competencia") or ""))


def load_config_demandas_empresa(empresa_id: int) -> set[str]:
    return load_empresa_demandas(int(empresa_id))


def save_config_demandas_empresa(empresa_id: int, lista_tipos: list[str], usuario: str | None = None) -> None:
    usuario = usuario or current_user()
    if not usuario_pode_criar_demandas_cliente(usuario, int(empresa_id)):
        log_permission_denied("CONFIG_DEMANDAS_CLIENTE", "empresas", int(empresa_id))
        raise PermissionError("Voce nao tem permissao para configurar demandas deste cliente.")
    timestamp = now_str()
    execute(
        "UPDATE empresa_demandas_config SET ativo=0, atualizado_em=?, atualizado_por=? WHERE empresa_id=?",
        (timestamp, usuario, int(empresa_id)),
    )
    for tipo in sorted({normalize_demanda_tipo(t) for t in lista_tipos if str(t or "").strip()}):
        tipo_id = demanda_tipo_id_by_code(tipo)
        if not tipo_id:
            continue
        execute(
            """
            INSERT INTO empresa_demandas_config
                (empresa_id, demanda_tipo_id, ativo, criado_em, atualizado_em, criado_por, atualizado_por)
            VALUES (?, ?, 1, ?, ?, ?, ?)
            ON CONFLICT(empresa_id, demanda_tipo_id) DO UPDATE SET
                ativo=1,
                atualizado_em=excluded.atualizado_em,
                atualizado_por=excluded.atualizado_por
            """,
            (int(empresa_id), int(tipo_id), timestamp, timestamp, usuario, usuario),
        )
    execute("DELETE FROM empresa_demandas WHERE empresa_id=?", (int(empresa_id),))
    for tipo in sorted({normalize_demanda_tipo(t) for t in lista_tipos}):
        execute(
            "INSERT INTO empresa_demandas (empresa_id, tipo) VALUES (?, ?) ON CONFLICT(empresa_id, tipo) DO NOTHING",
            (int(empresa_id), tipo),
        )
    log_action("Demandas", "CONFIG_EMPRESA", "empresas", int(empresa_id), usuario, ",".join(sorted(lista_tipos)))


def load_cliente_compartilhamentos(empresa_id: int) -> pd.DataFrame:
    return query_df(
        """
        SELECT id, empresa_id, contador_origem, contador_destino,
               COALESCE(pode_ver,1) AS pode_ver,
               COALESCE(pode_editar,0) AS pode_editar,
               COALESCE(pode_criar_demandas,0) AS pode_criar_demandas,
               COALESCE(ativo,1) AS ativo,
               criado_em, COALESCE(criado_por,'') AS criado_por
          FROM cliente_compartilhamentos
         WHERE empresa_id=?
         ORDER BY ativo DESC, contador_destino
        """,
        (int(empresa_id),),
    )


def salvar_compartilhamento_cliente(
    empresa_id: int,
    contador_destino: str,
    pode_ver: bool,
    pode_editar: bool,
    pode_criar_demandas: bool,
    usuario: str | None = None,
) -> None:
    usuario = normalize_username(usuario or current_user())
    if not can_share_cliente(int(empresa_id), usuario):
        log_permission_denied("COMPARTILHAR_CLIENTE", "empresas", int(empresa_id))
        raise PermissionError("Voce nao tem permissao para compartilhar este cliente.")
    row = empresa_row(int(empresa_id))
    origem = normalize_username(row.get("contador_responsavel")) or usuario
    destino = normalize_username(contador_destino)
    if not destino or destino == origem:
        raise ValueError("Selecione um contador destino diferente do responsavel.")
    existing = query_df(
        """
        SELECT id FROM cliente_compartilhamentos
         WHERE empresa_id=? AND UPPER(contador_origem)=UPPER(?) AND UPPER(contador_destino)=UPPER(?)
         LIMIT 1
        """,
        (int(empresa_id), origem, destino),
    )
    if existing.empty:
        execute(
            """
            INSERT INTO cliente_compartilhamentos
                (empresa_id, contador_origem, contador_destino, pode_ver, pode_editar,
                 pode_criar_demandas, criado_em, criado_por, ativo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (int(empresa_id), origem, destino, 1 if pode_ver else 0, 1 if pode_editar else 0, 1 if pode_criar_demandas else 0, now_str(), usuario),
        )
    else:
        execute(
            """
            UPDATE cliente_compartilhamentos
               SET pode_ver=?, pode_editar=?, pode_criar_demandas=?, ativo=1
             WHERE id=?
            """,
            (1 if pode_ver else 0, 1 if pode_editar else 0, 1 if pode_criar_demandas else 0, int(existing.iloc[0]["id"])),
        )
    execute("UPDATE empresas SET compartilhado=1, atualizado_em=? WHERE id=?", (now_str(), int(empresa_id)))


def remover_compartilhamento_cliente(compartilhamento_id: int, usuario: str | None = None) -> None:
    row_df = query_df("SELECT empresa_id FROM cliente_compartilhamentos WHERE id=?", (int(compartilhamento_id),))
    if row_df.empty:
        return
    empresa_id = int(row_df.iloc[0]["empresa_id"])
    if not can_share_cliente(empresa_id, usuario):
        log_permission_denied("REMOVER_COMPART_CLIENTE", "empresas", empresa_id)
        raise PermissionError("Voce nao tem permissao para remover compartilhamento.")
    execute("UPDATE cliente_compartilhamentos SET ativo=0 WHERE id=?", (int(compartilhamento_id),))


def load_cliente_estagiarios(empresa_id: int) -> pd.DataFrame:
    return query_df(
        """
        SELECT id, empresa_id, contador_responsavel, estagiario_username,
               COALESCE(pode_ver_cliente,1) AS pode_ver_cliente,
               COALESCE(pode_ver_demandas,1) AS pode_ver_demandas,
               COALESCE(pode_concluir_demandas,1) AS pode_concluir_demandas,
               COALESCE(pode_comentar,1) AS pode_comentar,
               COALESCE(ativo,1) AS ativo,
               criado_em, COALESCE(criado_por,'') AS criado_por
          FROM cliente_estagiarios
         WHERE empresa_id=?
         ORDER BY ativo DESC, estagiario_username
        """,
        (int(empresa_id),),
    )


def salvar_estagiario_cliente(
    empresa_id: int,
    estagiario_username: str,
    pode_ver_cliente: bool,
    pode_ver_demandas: bool,
    pode_concluir_demandas: bool,
    pode_comentar: bool,
    usuario: str | None = None,
) -> None:
    usuario = normalize_username(usuario or current_user())
    if not can_share_cliente(int(empresa_id), usuario):
        log_permission_denied("VINCULAR_ESTAGIARIO", "empresas", int(empresa_id))
        raise PermissionError("Voce nao tem permissao para vincular estagiario.")
    row = empresa_row(int(empresa_id))
    estagiario = normalize_username(estagiario_username)
    if not estagiario:
        raise ValueError("Selecione um estagiario.")
    existing = query_df(
        "SELECT id FROM cliente_estagiarios WHERE empresa_id=? AND UPPER(estagiario_username)=UPPER(?) LIMIT 1",
        (int(empresa_id), estagiario),
    )
    params = (
        int(empresa_id),
        normalize_username(row.get("contador_responsavel")) or "DMLIMA",
        estagiario,
        1 if pode_ver_cliente else 0,
        1 if pode_ver_demandas else 0,
        1 if pode_concluir_demandas else 0,
        1 if pode_comentar else 0,
        now_str(),
        usuario,
    )
    if existing.empty:
        execute(
            """
            INSERT INTO cliente_estagiarios
                (empresa_id, contador_responsavel, estagiario_username, pode_ver_cliente,
                 pode_ver_demandas, pode_concluir_demandas, pode_comentar, criado_em, criado_por, ativo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            params,
        )
    else:
        execute(
            """
            UPDATE cliente_estagiarios
               SET contador_responsavel=?, pode_ver_cliente=?, pode_ver_demandas=?,
                   pode_concluir_demandas=?, pode_comentar=?, ativo=1
             WHERE id=?
            """,
            (params[1], params[3], params[4], params[5], params[6], int(existing.iloc[0]["id"])),
        )


def remover_estagiario_cliente(vinculo_id: int, usuario: str | None = None) -> None:
    row_df = query_df("SELECT empresa_id FROM cliente_estagiarios WHERE id=?", (int(vinculo_id),))
    if row_df.empty:
        return
    empresa_id = int(row_df.iloc[0]["empresa_id"])
    if not can_share_cliente(empresa_id, usuario):
        log_permission_denied("REMOVER_ESTAGIARIO_CLIENTE", "empresas", empresa_id)
        raise PermissionError("Voce nao tem permissao para remover vinculo.")
    execute("UPDATE cliente_estagiarios SET ativo=0 WHERE id=?", (int(vinculo_id),))


def tipos_padrao_por_empresa(empresa: dict) -> set[str]:
    regime = str(empresa.get("regime") or "").upper()
    funcionarios = int(empresa.get("funcionarios", 0) or 0) == 1
    tipos: set[str] = set()
    if "MEI" in regime:
        tipos.update({"GUIA_MEI", "REL_MEI", "COBRAR_HONORARIOS"})
    elif "SIMPLES" in regime:
        tipos.update({"APUR_SIMPLES", "PUXAR_NF_SAIDA", "DEFIS", "REL_DEBITOS", "COBRAR_HONORARIOS"})
    else:
        tipos.update({"PUXAR_NF_SAIDA", "APUR_ISS", "GUIA_PREF", "REL_DEBITOS", "COBRAR_HONORARIOS"})
    if funcionarios:
        tipos.update({"EXEC_FOLHA", "ENV_CONTRACHEQUES", "GUIA_INSS", "GUIA_FGTS"})
    return tipos


def aplicar_regras_inteligentes_demanda(empresa: dict, tipos_configurados: set[str] | list[str]) -> set[str]:
    tipos = {normalize_demanda_tipo(t) for t in tipos_configurados if str(t or "").strip()}
    if not tipos:
        tipos = tipos_padrao_por_empresa(empresa)
    regime = str(empresa.get("regime") or "").upper()
    competencia = get_competencia_atual()
    ano_competencia = competencia.split("-", 1)[0]
    if "MEI" in regime:
        tipos.discard("APUR_SIMPLES")
        tipos.discard("DEFIS")
        tipos.add("GUIA_MEI")
        tipos.add("REL_MEI")
    else:
        tipos.discard("GUIA_MEI")
        tipos.discard("REL_MEI")
        if "SIMPLES" in regime:
            tipos.add("APUR_SIMPLES")
        tipos.add("PUXAR_NF_SAIDA")
    if int(empresa.get("funcionarios", 0) or 0):
        tipos.update({"EXEC_FOLHA", "GUIA_INSS", "GUIA_FGTS"})
        if "ENV_CONTRACHEQUES" in tipos:
            tipos.add("EXEC_FOLHA")
    else:
        for tipo in ["EXEC_FOLHA", "ENV_CONTRACHEQUES", "GUIA_INSS", "GUIA_FGTS"]:
            if tipo not in set(tipos_configurados):
                tipos.discard(tipo)
    if "ENV_CONTRACHEQUES" in tipos:
        tipos.add("EXEC_FOLHA")
    anos_quitados = {part.strip() for part in str(empresa.get("prefeitura_quitada_anos") or "").replace(";", ",").split(",") if part.strip()}
    if int(empresa.get("prefeitura_encerrada_ano_atual", 0) or 0) or ano_competencia in anos_quitados:
        tipos.discard("GUIA_PREF")
    if int(empresa.get("tem_parcelamento_mensal", 0) or 0):
        tipos.add("PARC_MENSAL")
    if int(empresa.get("tem_parcelamento_impostos", 0) or 0):
        tipos.add("PARC_IMPOSTOS")
    if "OUTRA" not in set(tipos_configurados):
        tipos.discard("OUTRA")
    return tipos


def gerar_demandas_por_config(competencia: str, usuario: str | None = None) -> dict:
    usuario = usuario or current_user()
    empresas = load_empresas_ativas()
    report = {"empresas_processadas": 0, "criadas": 0, "existentes": 0, "ignoradas": 0, "erros": []}
    for _, empresa in empresas.iterrows():
        try:
            empresa_dict = empresa.to_dict()
            config = load_config_demandas_empresa(int(empresa_dict["id"]))
            tipos = aplicar_regras_inteligentes_demanda(empresa_dict, config)
            report["empresas_processadas"] += 1
            if not tipos:
                report["ignoradas"] += 1
                continue
            for tipo in sorted(tipos, key=lambda code: next((row["ordem"] for row in DEMAND_TYPE_ROWS if row["nome_curto"] == code), 999)):
                created = create_demanda(int(empresa_dict["id"]), tipo, competencia, "config", responsavel=None)
                report["criadas" if created else "existentes"] += 1
            recalcular_liberacao_demandas(int(empresa_dict["id"]), competencia)
        except Exception as exc:
            report["erros"].append(f"{empresa.get('razao_social','')}: {exc}")
    log_action("Demandas", "GERAR_MES", "competencia", 0, usuario, json.dumps(report, ensure_ascii=False))
    return report


def reconciliar_demandas_competencia_por_config(competencia: str, usuario: str | None = None) -> dict:
    report = gerar_demandas_por_config(competencia, usuario or current_user())
    report["acao"] = "reconciliar"
    return report


def competencia_anterior(competencia: str) -> str:
    year, month = parse_competencia(competencia)
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


def propagar_pendencias_para_competencia(competencia_origem: str, competencia_destino: str, usuario: str | None = None) -> dict:
    usuario = usuario or current_user()
    pendencias = query_df(
        """
        SELECT d.id, d.empresa_id, d.tipo, COALESCE(d.responsavel,'') AS responsavel,
               COALESCE(d.prioridade,'normal') AS prioridade, COALESCE(d.observacao,'') AS observacao,
               COALESCE(e.is_ativo, CASE WHEN COALESCE(e.inativo,0)=1 THEN 0 ELSE 1 END) AS is_ativo
          FROM demandas d
          JOIN empresas e ON e.id=d.empresa_id
         WHERE d.competencia=?
           AND COALESCE(d.status,'pendente') NOT IN ('concluida','cancelada','dispensada')
           AND COALESCE(d.cancelada,0)=0
        """,
        (competencia_origem,),
    )
    report = {"origem": competencia_origem, "destino": competencia_destino, "criadas": 0, "existentes": 0, "ignoradas": 0, "erros": []}
    for _, row in pendencias.iterrows():
        if int(row.get("is_ativo", 0) or 0) != 1:
            report["ignoradas"] += 1
            continue
        try:
            created = create_demanda(
                int(row["empresa_id"]),
                str(row["tipo"]),
                competencia_destino,
                "propagada",
                str(row.get("responsavel") or ""),
                str(row.get("prioridade") or "normal"),
                str(row.get("observacao") or ""),
                "",
                int(row["id"]),
            )
            report["criadas" if created else "existentes"] += 1
        except Exception as exc:
            report["erros"].append(str(exc))
    log_action("Demandas", "PROPAGAR", "competencia", 0, usuario, json.dumps(report, ensure_ascii=False))
    return report


def load_demanda_status_history(demanda_id: int) -> pd.DataFrame:
    return query_df(
        """
        SELECT status_anterior, status_novo, COALESCE(observacao,'') AS observacao,
               COALESCE(usuario,'') AS usuario, criado_em
          FROM demanda_status_historico
         WHERE demanda_id=?
         ORDER BY criado_em DESC, id DESC
        """,
        (int(demanda_id),),
    )


def load_demanda_comentarios(demanda_id: int) -> pd.DataFrame:
    return query_df(
        """
        SELECT comentario, COALESCE(usuario,'') AS usuario, criado_em
          FROM demanda_comentarios
         WHERE demanda_id=?
         ORDER BY criado_em DESC, id DESC
        """,
        (int(demanda_id),),
    )


def add_demanda_comentario(demanda_id: int, comentario: str, usuario: str | None = None) -> None:
    usuario = usuario or current_user()
    if not usuario_pode_ver_demanda(usuario, int(demanda_id)):
        log_permission_denied("COMENTAR_DEMANDA", "demandas", int(demanda_id))
        raise PermissionError("Voce nao tem permissao para comentar esta demanda.")
    comentario = str(comentario or "").strip()
    if not comentario:
        raise ValueError("Informe o comentario.")
    execute(
        "INSERT INTO demanda_comentarios (demanda_id, comentario, usuario, criado_em) VALUES (?, ?, ?, ?)",
        (int(demanda_id), comentario, usuario, now_str()),
    )


def load_demanda_anexos(demanda_id: int) -> pd.DataFrame:
    return query_df(
        """
        SELECT nome_arquivo, url_arquivo, tipo_arquivo, COALESCE(usuario,'') AS usuario, criado_em
          FROM demanda_anexos
         WHERE demanda_id=?
         ORDER BY criado_em DESC, id DESC
        """,
        (int(demanda_id),),
    )


def add_demanda_anexo(demanda_id: int, nome_arquivo: str, url_arquivo: str, tipo_arquivo: str, usuario: str | None = None) -> None:
    if not str(url_arquivo or "").strip():
        raise ValueError("Informe o link do anexo.")
    execute(
        """
        INSERT INTO demanda_anexos (demanda_id, nome_arquivo, url_arquivo, tipo_arquivo, usuario, criado_em)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (int(demanda_id), str(nome_arquivo or "").strip(), str(url_arquivo or "").strip(), str(tipo_arquivo or "").strip(), usuario or current_user(), now_str()),
    )


def demand_order_value(tipo: str) -> int:
    code = normalize_demanda_tipo(tipo)
    for row in DEMAND_TYPE_ROWS:
        if row["nome_curto"] == code:
            return int(row["ordem"])
    return 999


def demandas_export_csv(df: pd.DataFrame) -> bytes:
    cols = [
        "competencia", "empresa", "cnpj", "regime", "contador_responsavel", "demanda",
        "status", "liberacao", "bloqueio", "responsavel_operacional", "prioridade", "data_limite", "observacao", "criado_em", "atualizado_em",
        "concluida_em", "concluida_por",
    ]
    export_df = df.copy()
    for col in cols:
        if col not in export_df.columns:
            export_df[col] = ""
    return export_df[cols].fillna("").to_csv(index=False).encode("utf-8-sig")


def render_setup() -> None:
    st.warning("Banco de dados ainda nao encontrado para este projeto web.")
    uploaded = st.file_uploader("Enviar cnpjs.db", type=["db", "sqlite", "sqlite3"])
    if uploaded:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        DEFAULT_DB_PATH.write_bytes(uploaded.getbuffer())
        st.success("Banco recebido. Recarregue a pagina para abrir o sistema.")
    if st.button("Criar banco vazio"):
        init_db()
        st.rerun()


def sync_auth_passwords_txt(users: dict[str, str]) -> None:
    return


def load_auth_users_from_file() -> dict[str, str]:
    if not AUTH_EXPORT_PATH.exists():
        return {}
    try:
        data = tomllib.loads(AUTH_EXPORT_PATH.read_text(encoding="utf-8"))
        raw_users = data.get("auth", {}).get("users", {})
        return {str(k): str(v) for k, v in dict(raw_users).items()}
    except Exception:
        return {}


def configured_users() -> dict[str, str]:
    users: dict[str, str] = load_auth_users_from_file()
    try:
        secrets_auth = st.secrets.get("auth", {})
        raw_users = secrets_auth.get("users", {}) if hasattr(secrets_auth, "get") else {}
        users.update({str(k): str(v) for k, v in dict(raw_users).items()})
    except Exception:
        pass

    env_user = os.getenv("CONTROLE_EMPRESAS_USER")
    env_password = os.getenv("CONTROLE_EMPRESAS_PASSWORD")
    if env_user and env_password:
        users[str(env_user)] = str(env_password)
    sync_auth_passwords_txt(users)
    return users


def require_login() -> bool:
    ensure_auth_sessions_table()
    if st.session_state.get("authenticated") or st.session_state.get("is_authenticated"):
        return True
    if _restore_persistent_auth_session():
        return True
    users = configured_users()
    if not users:
        with st.container(border=True, key="login_card"):
            st.markdown(
                """
                <div class="login-brand"><span class="login-mark">E</span>Excelencia Contabilidade</div>
                <div class="login-title">Controle de Empresas</div>
                <div class="login-subtitle">Acesso bloqueado. Configure usuarios em secrets ou variaveis de ambiente para liberar o acesso.</div>
                """,
                unsafe_allow_html=True,
            )
            st.warning(
                "Defina pelo menos um usuario em `.streamlit/secrets.toml` no formato `[auth.users]` "
                "ou use `CONTROLE_EMPRESAS_USER` e `CONTROLE_EMPRESAS_PASSWORD`.",
            )
        return False

    if st.session_state.get("authenticated"):
        if "page_label" not in st.session_state:
            st.session_state["page_label"] = AUTH_SESSION_DEFAULT_LABEL
        if "page" not in st.session_state:
            st.session_state["page"] = AUTH_SESSION_DEFAULT_PAGE
        with st.sidebar:
            user = st.session_state.get("auth_user", "")
            if user:
                st.caption(str(user))
            if st.button("Sair", help="Sair do sistema"):
                _logout_authenticated_session()
                st.rerun()
        return True

    with st.container(border=True, key="login_card"):
        st.markdown(
            """
            <div class="login-brand"><span class="login-mark">E</span>Excelencia Contabilidade</div>
            <div class="login-title">Controle de Empresas</div>
            <div class="login-subtitle">Acesso restrito ao controle operacional.</div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("login_form"):
            user = st.text_input("Usuario")
            password = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar")
    if submitted:
        if users.get(user) == password:
            token = create_auth_session(user)
            _set_auth_persistence(token)
            st.session_state["authenticated"] = True
            st.session_state["auth_user"] = user
            st.session_state["page_label"] = AUTH_SESSION_DEFAULT_LABEL
            st.session_state["page"] = AUTH_SESSION_DEFAULT_PAGE
            st.query_params["page"] = AUTH_SESSION_DEFAULT_PAGE
            st.rerun()
        else:
            st.error("Usuario ou senha invalidos.")
    return False


def render_sidebar() -> tuple[str, str]:
    menu_map = {
        "📂 Módulos": "Modulos",
        "📊 Painel": "Painel",
        "👤 Novo Cliente": "Novo Cliente",
        "🏢 Empresas": "Empresas",
        "📋 Demandas": "Demandas",
        "🤖 Automação": "Automacao",
        "💰 Faturamento": "Faturamento",
        "💾 Backup": "Backup",
    }
    menu_items = list(menu_map.keys())
    requested_page = normalize_page(st.query_params.get("page", st.session_state.get("page", "Modulos")) or "Modulos")
    requested_label = next((label for label, page in menu_map.items() if page == requested_page), "📂 Módulos")
    if requested_label not in menu_items:
        requested_label = st.session_state.get("page_label", "📂 Módulos")
    if requested_label not in menu_items:
        requested_label = "📂 Módulos"
    menu_index = menu_items.index(requested_label)
    with st.sidebar:
        render_company_logo()
        page_label = st.radio("Menu", menu_items, index=menu_index)
        page = menu_map[page_label]
        st.session_state["page_label"] = page_label
        st.session_state["page"] = page
        if st.query_params.get("page") != page:
            st.query_params["page"] = page
        saved_competencia = (
            st.session_state.get("competencia")
            or st.session_state.get("ultima_competencia")
            or get_setting("ultima_competencia", current_competencia())
        )
        st.session_state["ultima_competencia"] = saved_competencia
        current_year, current_month = parse_competencia(saved_competencia)
        years = list(range(current_year - 5, current_year + 6))
        month_options = [f"{m:02d}" for m in range(1, 13)]
        y1, y2 = st.sidebar.columns(2)
        year = y1.selectbox("Ano", years, index=years.index(current_year))
        month = y2.selectbox("Mes", month_options, index=month_options.index(f"{current_month:02d}"))
        competencia = f"{int(year)}-{month}"
        st.session_state["competencia"] = competencia
        if st.session_state.get("ultima_competencia") != competencia:
            st.session_state["ultima_competencia"] = competencia
            set_setting("ultima_competencia", competencia)
        touch_active_session(page)
        active_now = load_active_sessions()
        st.sidebar.caption(f"Usuarios online: {active_now['usuario'].nunique()} | Sessoes: {len(active_now)}")
        if not active_now.empty:
            names = ", ".join(active_now["usuario"].drop_duplicates().tolist()[:4])
            st.sidebar.caption(names)
    return page, competencia


def require_login_secure() -> bool:
    ensure_database_ready()
    ensure_auth_sessions_table()
    if _restore_persistent_auth_session():
        return True
    legacy_users = configured_users()
    total_users = query_df("SELECT COUNT(*) AS total FROM users")
    has_users = not total_users.empty and int(total_users.iloc[0]["total"] or 0) > 0
    has_legacy = bool(legacy_users)
    if not has_users and not has_legacy:
        with st.container(border=True, key="login_card_secure"):
            st.markdown(
                """
                <div class="login-brand"><span class="login-mark">E</span>Excelencia Contabilidade</div>
                <div class="login-title">Controle de Empresas</div>
                <div class="login-subtitle">Acesso bloqueado. Configure usuários na tabela, em secrets ou por variável de ambiente.</div>
                """,
                unsafe_allow_html=True,
            )
            st.warning(
                "Defina ao menos um usuário em `users`, `[auth.users]` no secrets.toml ou via `CONTROLE_EMPRESAS_USER`/`CONTROLE_EMPRESAS_PASSWORD`.",
            )
        return False

    if st.session_state.get("authenticated") or st.session_state.get("is_authenticated"):
        username = current_username()
        user_row = get_user_row(username)
        if user_row and int(user_row.get("ativo", 1) or 0) == 0:
            remove_active_session()
            _logout_authenticated_session()
            st.error("Usuário inativo. Procure o administrador.")
            return False
        if user_row:
            st.session_state["user_role"] = user_role_for(username, user_row.get("role", "usuario"))
            st.session_state["user_name"] = user_display_name_for(username, user_row.get("nome", username))
        if "page_label" not in st.session_state:
            st.session_state["page_label"] = AUTH_SESSION_DEFAULT_LABEL
        if "page" not in st.session_state:
            st.session_state["page"] = AUTH_SESSION_DEFAULT_PAGE
        return True

    with st.container(border=True, key="login_card_secure"):
        st.markdown(
            """
            <div class="login-brand"><span class="login-mark">E</span>Excelencia Contabilidade</div>
            <div class="login-title">Controle de Empresas</div>
            <div class="login-subtitle">Acesso restrito ao controle operacional.</div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("login_form_secure"):
            user = st.text_input("Usuario")
            password = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar")
    if submitted:
        username_norm = normalize_username(user)
        user_row = get_user_row(username_norm)
        if user_row and int(user_row.get("ativo", 1) or 0) == 0:
            st.error("Usuário inativo. Procure o administrador.")
            return False
        if user_row and verify_password(password, user_row.get("senha_hash", "")):
            set_authenticated_session(username_norm, user_row.get("role", "usuario"), user_row.get("nome", username_norm))
            token = create_auth_session(username_norm)
            _set_auth_persistence(token)
            update_user_last_login(username_norm)
            st.session_state["page_label"] = AUTH_SESSION_DEFAULT_LABEL
            st.session_state["page"] = AUTH_SESSION_DEFAULT_PAGE
            st.query_params["page"] = AUTH_SESSION_DEFAULT_PAGE
            st.rerun()
        legacy_password = legacy_users.get(username_norm)
        if legacy_password and legacy_password == password:
            role = user_role_for(username_norm, user_row.get("role", "usuario") if user_row else "usuario")
            nome = user_display_name_for(username_norm, user_row.get("nome", username_norm) if user_row else username_norm)
            if user_row:
                execute(
                    """
                    UPDATE users
                       SET senha_hash=COALESCE(NULLIF(senha_hash,''), ?),
                           role=?,
                           ativo=1,
                           nome=COALESCE(NULLIF(nome,''), ?),
                           responsavel=COALESCE(NULLIF(responsavel,''), ?),
                           atualizado_em=?,
                           ultimo_login=?
                     WHERE UPPER(username)=UPPER(?)
                    """,
                    (hash_password(password), role, nome, username_norm, now_str(), now_str(), username_norm),
                )
            else:
                upsert_user_record(
                    username=username_norm,
                    nome=nome,
                    senha_hash=hash_password(password),
                    role=role,
                    ativo=1,
                    criado_por=username_norm,
                    responsavel=username_norm,
                    observacao="Migrado automaticamente do login legado.",
                    ultimo_login=now_str(),
                )
            set_authenticated_session(username_norm, role, nome)
            token = create_auth_session(username_norm)
            _set_auth_persistence(token)
            update_user_last_login(username_norm)
            st.session_state["page_label"] = AUTH_SESSION_DEFAULT_LABEL
            st.session_state["page"] = AUTH_SESSION_DEFAULT_PAGE
            st.query_params["page"] = AUTH_SESSION_DEFAULT_PAGE
            st.rerun()
        else:
            st.error("Usuario ou senha invalidos.")
    return False


def render_sidebar_secure() -> tuple[str, str]:
    menu_map = {
        "📂 Módulos": "Modulos",
        "📊 Painel": "Painel",
        "👤 Novo Cliente": "Novo Cliente",
        "🏢 Empresas": "Empresas",
        "📋 Demandas": "Demandas",
        "🤖 Automação": "Automacao",
        "💰 Faturamento": "Faturamento",
        "💾 Backup": "Backup",
    }
    if can_access_users_page():
        menu_map["👥 Usuários"] = "usuarios"

    requested_page = normalize_page(st.query_params.get("page", st.session_state.get("page", "Modulos")) or "Modulos")
    if requested_page == "usuarios" and not can_access_users_page():
        st.warning("Você não tem permissão para acessar esta área.")
        requested_page = "Modulos"
        st.query_params["page"] = "Modulos"
        st.session_state["page"] = "Modulos"
        st.session_state["page_label"] = "📂 Módulos"

    requested_label = next((label for label, page in menu_map.items() if page == requested_page), "📂 Módulos")
    if requested_label not in menu_map:
        requested_label = st.session_state.get("page_label", "📂 Módulos")
    if requested_label not in menu_map:
        requested_label = "📂 Módulos"
    menu_items = list(menu_map.keys())
    menu_index = menu_items.index(requested_label)

    with st.sidebar:
        render_company_logo(72)
        st.markdown(
            f"<div style='margin:0.08rem 0 0.03rem 0; line-height:1.05;'><strong>Usuário:</strong> {current_user_display_name()}</div>"
            f"<div style='margin:0 0 0.08rem 0; line-height:1; color:var(--nexus-muted); font-size:0.88rem;'>Perfil: {user_role_label(current_user_role())}</div>",
            unsafe_allow_html=True,
        )
        page_label = requested_label
        page = requested_page
        st.session_state["page_label"] = page_label
        st.session_state["page"] = page
        if st.query_params.get("page") != page:
            st.query_params["page"] = page

        saved_competencia = (
            st.session_state.get("competencia")
            or st.session_state.get("ultima_competencia")
            or get_setting("ultima_competencia", current_competencia())
        )
        st.session_state["ultima_competencia"] = saved_competencia
        current_year, current_month = parse_competencia(saved_competencia)
        years = list(range(current_year - 5, current_year + 6))
        month_options = [f"{m:02d}" for m in range(1, 13)]
        y1, y2 = st.sidebar.columns(2)
        year = y1.selectbox("Ano", years, index=years.index(current_year), key="ano_secure")
        month = y2.selectbox("Mes", month_options, index=month_options.index(f"{current_month:02d}"), key="mes_secure")
        competencia = f"{int(year)}-{month}"
        st.session_state["competencia"] = competencia
        if st.session_state.get("ultima_competencia") != competencia:
            st.session_state["ultima_competencia"] = competencia
            set_setting("ultima_competencia", competencia)
        touch_active_session(page)
        active_now = load_active_sessions()
        st.caption(f"Online: {active_now['usuario'].nunique()} | Sessões: {len(active_now)}")
    return page, competencia


def render_usuarios() -> None:
    if not can_access_users_page():
        st.warning("Você não tem permissão para acessar esta área.")
        st.stop()

    st.title("Gestão de Usuários")
    st.caption("Crie, visualize e gerencie acessos ao sistema.")

    all_users = get_users_df()
    visible_users = get_visible_users_df()
    scope_df = visible_users.copy()

    if is_admin_geral():
        total_users = len(all_users)
        active_users = int((all_users["ativo"] == 1).sum()) if not all_users.empty else 0
        inactive_users = int((all_users["ativo"] == 0).sum()) if not all_users.empty else 0
        active_now = load_active_sessions()
        online_users = active_now["usuario"].nunique()
    else:
        total_users = len(scope_df)
        active_users = int((scope_df["ativo"] == 1).sum()) if not scope_df.empty else 0
        inactive_users = int((scope_df["ativo"] == 0).sum()) if not scope_df.empty else 0
        active_now = load_active_sessions()
        if not scope_df.empty:
            allowed_users = set(scope_df["username"].astype(str).str.upper().tolist())
            online_users = int(active_now["usuario"].astype(str).str.upper().isin(allowed_users).sum())
        else:
            online_users = 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total", total_users)
    c2.metric("Ativos", active_users)
    c3.metric("Inativos", inactive_users)
    c4.metric("Online", int(online_users))

    if is_admin_geral() and not all_users.empty:
        role_counts = all_users["role"].fillna("usuario").value_counts().to_dict()
        cols = st.columns(min(4, len(role_counts)) or 1)
        for idx, (role, qty) in enumerate(role_counts.items()):
            cols[idx % len(cols)].metric(user_role_label(role), int(qty))

    filters = st.columns([1.3, 0.8, 0.8])
    search = filters[0].text_input("Buscar por nome ou login", key="usuarios_busca")
    role_options = ["Todos"] + list(USER_ROLES.keys())
    role_filter = filters[1].selectbox("Perfil", role_options, key="usuarios_perfil")
    status_filter = filters[2].selectbox("Status", ["Todos", "Ativos", "Inativos"], key="usuarios_status")

    filtered = scope_df.copy()
    if not filtered.empty and search:
        mask = (
            filtered["username"].astype(str).str.contains(search, case=False, na=False)
            | filtered["nome"].astype(str).str.contains(search, case=False, na=False)
        )
        filtered = filtered.loc[mask].copy()
    if not filtered.empty and role_filter != "Todos":
        filtered = filtered.loc[filtered["role"].astype(str).eq(role_filter)].copy()
    if not filtered.empty and status_filter == "Ativos":
        filtered = filtered.loc[filtered["ativo"] == 1].copy()
    if not filtered.empty and status_filter == "Inativos":
        filtered = filtered.loc[filtered["ativo"] == 0].copy()

    st.dataframe(
        filtered[["id", "username", "nome", "role", "ativo", "responsavel", "criado_por", "criado_em", "atualizado_em", "ultimo_login", "observacao"]]
        if not filtered.empty
        else filtered,
        use_container_width=True,
        hide_index=True,
        column_config={
            "id": st.column_config.NumberColumn("id"),
            "username": st.column_config.TextColumn("username"),
            "nome": st.column_config.TextColumn("nome"),
            "role": st.column_config.TextColumn("role"),
            "ativo": st.column_config.NumberColumn("ativo"),
            "responsavel": st.column_config.TextColumn("responsavel"),
            "criado_por": st.column_config.TextColumn("criado_por"),
            "criado_em": st.column_config.TextColumn("criado_em"),
            "atualizado_em": st.column_config.TextColumn("atualizado_em"),
            "ultimo_login": st.column_config.TextColumn("ultimo_login"),
            "observacao": st.column_config.TextColumn("observacao"),
        },
    )

    if can_manage_users():
        with st.expander("+ Criar novo usuário", expanded=is_admin_geral()):
            with st.form("create_user_form", clear_on_submit=True):
                nome = st.text_input("Nome")
                username = st.text_input("Usuário/login")
                if is_admin_geral():
                    role = st.selectbox("Perfil", list(USER_ROLES.keys()), index=3)
                    responsavel = st.text_input("Responsável")
                else:
                    role = st.selectbox("Perfil", ["estagiario", "usuario"], index=0)
                    responsavel = st.text_input("Responsável", value="RAFAEL", disabled=True)
                senha = st.text_input("Senha", type="password")
                confirmar = st.text_input("Confirmar senha", type="password")
                ativo = st.checkbox("Ativo", value=True)
                observacao = st.text_area("Observação")
                submit_create = st.form_submit_button("Criar usuário")
            if submit_create:
                username_norm = normalize_username(username)
                if not username_norm:
                    st.error("Usuário/login é obrigatório.")
                elif get_user_row(username_norm):
                    st.error("Já existe um usuário com esse login.")
                elif not senha or not confirmar:
                    st.error("Informe a senha e a confirmação.")
                elif len(senha) < PASSWORD_MIN_LENGTH:
                    st.error(f"A senha deve ter pelo menos {PASSWORD_MIN_LENGTH} caracteres.")
                elif senha != confirmar:
                    st.error("Senha e confirmação não conferem.")
                elif not is_admin_geral() and role not in {"estagiario", "usuario"}:
                    st.error("RAFAEL não pode criar esse perfil.")
                else:
                    responsavel_final = normalize_username(responsavel) if is_admin_geral() else "RAFAEL"
                    if not is_admin_geral():
                        responsavel_final = "RAFAEL"
                    upsert_user_record(
                        username=username_norm,
                        nome=nome or username_norm,
                        senha_hash=hash_password(senha),
                        role=role,
                        ativo=1 if ativo else 0,
                        criado_por=current_username(),
                        responsavel=responsavel_final or username_norm,
                        observacao=observacao,
                    )
                    st.success("Usuário criado com sucesso.")
                    st.rerun()

    if filtered.empty:
        st.info("Nenhum usuário encontrado com os filtros aplicados.")
        return

    for _, row in filtered.sort_values(["username"]).iterrows():
        username = str(row["username"])
        display_title = f'{username} - {row.get("nome", "")}'.strip(" -")
        with st.expander(display_title, expanded=False):
            editable = can_manage_user(row)
            if not editable:
                st.info("Você não tem permissão para editar este usuário.")
                continue
            row_role = str(row.get("role") or "usuario")
            is_special_user = normalize_username(username) in SPECIAL_USER_ROLES
            with st.form(f"edit_user_{row['id']}"):
                nome = st.text_input("Nome", value=str(row.get("nome", "")))
                if is_admin_geral() and not is_special_user:
                    role = st.selectbox("Perfil", list(USER_ROLES.keys()), index=list(USER_ROLES.keys()).index(row_role) if row_role in USER_ROLES else 3)
                    responsavel = st.text_input("Responsável", value=str(row.get("responsavel", "")))
                    criado_por = st.text_input("Criado por", value=str(row.get("criado_por", "")))
                else:
                    role = row_role
                    responsavel = str(row.get("responsavel", ""))
                    criado_por = str(row.get("criado_por", ""))
                    st.text_input("Perfil", value=user_role_label(role), disabled=True)
                    st.text_input("Responsável", value=responsavel, disabled=True)
                ativo = st.checkbox("Ativo", value=int(row.get("ativo", 1) or 1) == 1)
                observacao = st.text_area("Observação", value=str(row.get("observacao", "")))
                submit_edit = st.form_submit_button("Salvar alterações")
            if submit_edit:
                role_final = row_role if not is_admin_geral() or is_special_user else role
                if not is_admin_geral() and role_final not in {"estagiario", "usuario", "contador"}:
                    st.error("Perfil não permitido para este usuário.")
                    continue
                if normalize_username(username) == "DMLIMA":
                    role_final = "admin_geral"
                    responsavel = "DMLIMA"
                if normalize_username(username) == "RAFAEL":
                    role_final = "contador"
                    responsavel = "RAFAEL"
                if int(row.get("ativo", 1) or 1) == 1 and not ativo and not can_disable_user_record(row.to_dict()):
                    st.error("Não é permitido desativar o último administrador ativo.")
                    continue
                execute(
                    """
                    UPDATE users
                       SET nome=?,
                           role=?,
                           ativo=?,
                           responsavel=?,
                           criado_por=?,
                           observacao=?,
                           atualizado_em=?
                     WHERE id=?
                    """,
                    (
                        nome,
                        role_final,
                        1 if ativo else 0,
                        normalize_username(responsavel) or normalize_username(username),
                        normalize_username(criado_por) or str(row.get("criado_por", "")),
                        observacao,
                        now_str(),
                        int(row["id"]),
                    ),
                )
                st.success("Usuário atualizado.")
                st.rerun()

            col_a, col_b, col_c = st.columns(3)
            with col_a:
                if int(row.get("ativo", 1) or 1) == 1:
                    disable_confirm = st.checkbox("Confirmo a desativação", key=f"disable_confirm_{row['id']}")
                    if st.button("Desativar", key=f"disable_btn_{row['id']}", disabled=not disable_confirm):
                        if not can_disable_user_record(row.to_dict()):
                            st.error("Não é permitido desativar o último administrador ativo.")
                        else:
                            execute("UPDATE users SET ativo=0, atualizado_em=? WHERE id=?", (now_str(), int(row["id"])))
                            st.success("Usuário desativado.")
                            st.rerun()
                else:
                    if st.button("Reativar", key=f"reactivate_btn_{row['id']}"):
                        execute("UPDATE users SET ativo=1, atualizado_em=? WHERE id=?", (now_str(), int(row["id"])))
                        st.success("Usuário reativado.")
                        st.rerun()
            with col_b:
                with st.form(f"reset_pwd_{row['id']}"):
                    nova_senha = st.text_input("Nova senha", type="password")
                    confirmar_nova = st.text_input("Confirmar nova senha", type="password")
                    submit_reset = st.form_submit_button("Resetar senha")
                if submit_reset:
                    if not nova_senha or len(nova_senha) < PASSWORD_MIN_LENGTH:
                        st.error(f"A senha deve ter pelo menos {PASSWORD_MIN_LENGTH} caracteres.")
                    elif nova_senha != confirmar_nova:
                        st.error("Senha e confirmação não conferem.")
                    else:
                        execute(
                            "UPDATE users SET senha_hash=?, atualizado_em=? WHERE id=?",
                            (hash_password(nova_senha), now_str(), int(row["id"])),
                        )
                        st.success("Senha redefinida.")
                        st.rerun()
            with col_c:
                st.caption(f"Criado em: {row.get('criado_em', '')}")
                st.caption(f"Último login: {row.get('ultimo_login', '')}")


def render_modulos() -> None:
    st.subheader("Modulos")
    cols = st.columns(2)
    if cols[0].button("Cadastro de Empresas", key="module_open_empresas_simple", use_container_width=True):
        navigate_to("Empresas")
    if cols[1].button("Controle de Demandas", key="module_open_demandas_simple", use_container_width=True, type="primary"):
        navigate_to("Demandas")
    return

    st.markdown(
        """
        <div class="launcher-shell">
            <div class="launcher-kicker">Portal Principal | Selecao de modulo</div>
            <div class="launcher-title">Acesso ao SISTEMA EXCELENCIA CONTABILIDADE</div>
            <div class="launcher-subtitle">Selecione o ambiente de trabalho para iniciar sua operacao.</div>
        </div>
        <div class="launcher-grid-wrap">
        """,
        unsafe_allow_html=True,
    )
    for start in range(0, len(MODULES), 2):
        cols = st.columns(2)
        for idx, item in enumerate(MODULES[start:start + 2]):
            with cols[idx]:
                enabled = bool(item.get("enabled"))
                safe_key = str(item["title"]).replace(" ", "_").replace("/", "_")
                disabled_class = "" if enabled else " disabled"
                st.markdown(
                    f"""
                    <div class="module-card{disabled_class}">
                        <div class="module-head">
                            <span class="module-title">{item['title']}</span>
                            <span class="module-tag">{item['tag']}</span>
                        </div>
                        <div class="module-desc">{item['desc']}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if enabled:
                    target = normalize_page(str(item["page"]))
                    label = next((menu_label for menu_label, menu_page in NAV_MENU.items() if menu_page == target), item["title"])
                    if st.button("🚀 Acessar módulo", key=f"module_open_{safe_key}", use_container_width=False):
                        navigate_to_page(target, label)
                else:
                    st.button("Disponível em breve", key=f"module_disabled_{safe_key}", disabled=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_painel(competencia: str) -> None:
    empresas = load_empresas(active_only=False)
    demandas = load_demandas(competencia)
    faturamento_mei = query_df(
        """
        SELECT f.id, f.empresa_id, e.razao_social, f.competencia, f.valor,
               COALESCE(f.valor_nota_fiscal,0) AS valor_nota_fiscal,
               COALESCE(f.valor_mov_extrato,0) AS valor_mov_extrato,
               COALESCE(f.observacao,'') AS observacao
          FROM faturamento_mei f
          JOIN empresas e ON e.id=f.empresa_id
         WHERE f.competencia=?
         ORDER BY e.razao_social COLLATE NOCASE
        """,
        (competencia,),
    )

    total_empresas = len(empresas)
    empresas_ativas = int((empresas["is_ativo"] == 1).sum()) if not empresas.empty else 0
    empresas_inativas = int((empresas["is_ativo"] == 0).sum()) if not empresas.empty else 0
    total_demandas = len(demandas)
    concluidas = int((demandas["feito"] == 1).sum()) if not demandas.empty else 0
    pendentes = int((demandas["feito"] == 0).sum()) if not demandas.empty else 0
    receita_mei = float(faturamento_mei["valor"].fillna(0).sum()) if not faturamento_mei.empty else 0.0
    faturamento_nf = float(faturamento_mei["valor_nota_fiscal"].fillna(0).sum()) if not faturamento_mei.empty else 0.0
    faturamento_extrato = float(faturamento_mei["valor_mov_extrato"].fillna(0).sum()) if not faturamento_mei.empty else 0.0

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Empresas", total_empresas)
    c2.metric("Ativas", empresas_ativas)
    c3.metric("Inativas", empresas_inativas)
    c4.metric("Demandas do mes", total_demandas)
    c5.metric("Concluidas", concluidas)
    c6.metric("Pendentes", pendentes)

    st.caption(f"Competencia selecionada: {competencia}")

    if demandas.empty:
        st.info("Sem demandas para esta competencia. O painel continua mostrando os demais indicadores do banco.")

    resumo = pd.DataFrame()
    if not demandas.empty:
        resumo = (
            demandas.groupby(["tipo", "demanda", "status"])
            .size()
            .reset_index(name="qtd")
            .sort_values(["tipo", "status"])
        )

    left, right = st.columns([1.1, 0.9])
    with left:
        st.subheader("Resumo por demanda")
        if resumo.empty:
            st.write("Sem dados para consolidar nesta competencia.")
        else:
            resumo_chart = resumo.pivot_table(index="demanda", columns="status", values="qtd", aggfunc="sum", fill_value=0)
            st.bar_chart(resumo_chart)
            show_table(
                resumo[["demanda", "status", "qtd"]],
                key=f"painel_resumo_{competencia}",
                height=260,
                editable=False,
                disabled=True,
                column_config={
                    "demanda": st.column_config.TextColumn("Demanda", width=260),
                    "status": st.column_config.TextColumn("Status", width=120),
                    "qtd": st.column_config.NumberColumn("Qtd", width=80),
                },
            )
    with right:
        st.subheader("Faturamento MEI")
        mc1, mc2 = st.columns(2)
        mc1.metric("Total", f"R$ {receita_mei:,.2f}")
        mc2.metric("NF", f"R$ {faturamento_nf:,.2f}")
        st.metric("Extrato", f"R$ {faturamento_extrato:,.2f}")
        if faturamento_mei.empty:
            st.info("Sem faturamento MEI para esta competencia.")
        else:
            st.dataframe(
                faturamento_mei[["razao_social", "valor", "valor_nota_fiscal", "valor_mov_extrato", "observacao"]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "razao_social": st.column_config.TextColumn("Empresa", width=220),
                    "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                    "valor_nota_fiscal": st.column_config.NumberColumn("NF", format="R$ %.2f"),
                    "valor_mov_extrato": st.column_config.NumberColumn("Extrato", format="R$ %.2f"),
                    "observacao": st.column_config.TextColumn("Observacao", width=180),
                },
            )

    c_left, c_right = st.columns([1.05, 0.95])
    with c_left:
        st.subheader("Pendencias")
        pendentes_df = demandas[demandas["feito"] == 0][["demanda", "razao_social", "cnpj", "regime", "observacao"]] if not demandas.empty else demandas
        if pendentes_df.empty:
            st.success("Nenhuma pendencia aberta nesta competencia.")
        else:
            show_table(
                pendentes_df,
                key=f"painel_pendentes_{competencia}",
                height=320,
                editable=False,
                disabled=True,
                column_config={
                    "demanda": st.column_config.TextColumn("Demanda", width=220),
                    "razao_social": st.column_config.TextColumn("Razao social", width=300),
                    "cnpj": st.column_config.TextColumn("CNPJ", width=150),
                    "regime": st.column_config.TextColumn("Regime", width=120),
                    "observacao": st.column_config.TextColumn("Observacao", width=260),
                },
            )

    with c_right:
        st.subheader("Leitura rapida")
        regime_counts = empresas[empresas["is_ativo"] == 1]["regime"].replace("", "Sem regime").value_counts().reset_index()
        regime_counts.columns = ["regime", "qtd"]
        if regime_counts.empty:
            st.info("Sem empresas ativas para resumir por regime.")
        else:
            st.bar_chart(regime_counts.set_index("regime"))

        if not demandas.empty:
            top_pendentes = (
                demandas[demandas["feito"] == 0]
                .groupby(["razao_social", "cnpj"])
                .size()
                .reset_index(name="pendencias")
                .sort_values(["pendencias", "razao_social"], ascending=[False, True])
                .head(8)
            )
            st.caption("Top clientes com pendencias")
            if top_pendentes.empty:
                st.write("Sem pendencias por cliente.")
            else:
                show_table(
                    top_pendentes,
                    key=f"painel_top_pendencias_{competencia}",
                    height=220,
                    editable=False,
                    disabled=True,
                    column_config={
                        "razao_social": st.column_config.TextColumn("Cliente", width=260),
                        "cnpj": st.column_config.TextColumn("CNPJ", width=150),
                        "pendencias": st.column_config.NumberColumn("Pendencias", width=100),
                    },
                )

    if not demandas.empty:
        st.subheader("Ultimas movimentacoes")
        ultimas = demandas.sort_values(["atualizado_em", "id"], ascending=[False, False]).head(12)
        show_table(
            ultimas[["demanda", "razao_social", "status", "atualizado_em", "observacao"]],
            key=f"painel_ultimas_{competencia}",
            height=260,
            editable=False,
            disabled=True,
            column_config={
                "demanda": st.column_config.TextColumn("Demanda", width=220),
                "razao_social": st.column_config.TextColumn("Razao social", width=280),
                "status": st.column_config.TextColumn("Status", width=110),
                "atualizado_em": st.column_config.TextColumn("Atualizado em", width=160),
                "observacao": st.column_config.TextColumn("Observacao", width=240),
            },
        )


def reset_empresa_cadastro_on_state() -> None:
    st.session_state["empresa_cadastro_on_open"] = False
    st.session_state["empresa_cadastro_on_mode"] = "lookup"
    st.session_state["empresa_cadastro_on_result"] = {}
    st.session_state["empresa_cadastro_on_error"] = ""
    st.session_state["empresa_cadastro_on_existing_id"] = 0
    st.session_state["empresa_cadastro_on_lookup_value"] = ""


def render_empresa_cadastro_on_panel() -> None:
    if not st.session_state.get("empresa_cadastro_on_open", False):
        return

    with st.container(border=True):
        st.markdown("<h5 style='margin-top: 0px; margin-bottom: 4px;'>Cadastro On / Incluir por CNPJ</h5>", unsafe_allow_html=True)
        st.caption("Digite apenas o CNPJ. Se existir na base, o sistema oferece atualizar os dados cadastrais.")
        with st.form("empresa_cadastro_on_lookup_form", clear_on_submit=False):
            cnpj_lookup = st.text_input("CNPJ", value=str(st.session_state.get("empresa_cadastro_on_lookup_value", "")))
            c1, c2 = st.columns(2)
            submit_lookup = c1.form_submit_button(f"{BUTTON_LABELS['buscar']} e incluir", type="primary")
            cancel_lookup = c2.form_submit_button(BUTTON_LABELS["cancelar"], key="btn_cadastro_on_cancelar")

        if cancel_lookup:
            reset_empresa_cadastro_on_state()
            st.rerun()

        if submit_lookup:
            digits = cnpj_digits(cnpj_lookup)
            st.session_state["empresa_cadastro_on_lookup_value"] = digits
            if len(digits) != 14:
                st.session_state["empresa_cadastro_on_error"] = "CNPJ invalido. Informe 14 digitos."
                st.session_state["empresa_cadastro_on_mode"] = "manual"
                st.rerun()

            existing = empresa_row_by_cnpj(normalize_cnpj(digits))
            try:
                lookup_data = fetch_empresa_cadastro_on(digits)
                lookup_data["cnpj"] = digits
                if existing:
                    st.session_state["empresa_cadastro_on_result"] = lookup_data
                    st.session_state["empresa_cadastro_on_existing_id"] = int(existing.get("id", 0) or 0)
                    st.session_state["empresa_cadastro_on_error"] = "CNPJ ja cadastrado. Use a atualizacao para trazer os dados cadastrais mais recentes."
                    st.session_state["empresa_cadastro_on_mode"] = "review"
                    st.rerun()

                save_empresa(lookup_data, None)
                st.session_state["empresa_save_notice"] = f"Cliente incluido com sucesso por CNPJ {normalize_cnpj(digits)}."
                reset_empresa_cadastro_on_state()
                st.rerun()
            except Exception as exc:
                st.session_state["empresa_cadastro_on_error"] = str(exc)
                st.session_state["empresa_cadastro_on_mode"] = "manual"
                if existing:
                    st.session_state["empresa_cadastro_on_result"] = existing
                    st.session_state["empresa_cadastro_on_existing_id"] = int(existing.get("id", 0) or 0)
                st.rerun()

        if st.session_state.get("empresa_cadastro_on_error"):
            st.error(st.session_state["empresa_cadastro_on_error"])

        if st.session_state.get("empresa_cadastro_on_mode") == "review" and st.session_state.get("empresa_cadastro_on_result"):
            review_data = st.session_state["empresa_cadastro_on_result"]
            existing_id = int(st.session_state.get("empresa_cadastro_on_existing_id", 0) or 0)
            st.info(
                f"CNPJ localizado. Razao social: {review_data.get('razao_social', '')}. "
                "Clique para atualizar os dados cadastrais do cliente existente."
            )
            c1, c2 = st.columns(2)
            if c1.button(f"{BUTTON_LABELS['atualizar']} dados cadastrais", key="btn_cadastro_on_atualizar", type="primary", use_container_width=True):
                save_empresa(review_data, existing_id)
                st.session_state["empresa_save_notice"] = f"Dados cadastrais atualizados para {normalize_cnpj(review_data.get('cnpj', ''))}."
                reset_empresa_cadastro_on_state()
                st.rerun()
            if c2.button(BUTTON_LABELS["cancelar"], key="btn_cadastro_on_cancelar_review", use_container_width=True):
                reset_empresa_cadastro_on_state()
                st.rerun()

        if st.session_state.get("empresa_cadastro_on_mode") == "manual":
            base_row = st.session_state.get("empresa_cadastro_on_result") or {}
            with st.form("empresa_cadastro_on_manual_form", clear_on_submit=False):
                m1, m2 = st.columns(2)
                manual_cnpj = m1.text_input("CNPJ", value=st.session_state.get("empresa_cadastro_on_lookup_value", ""))
                manual_razao = m2.text_input("Razao social", value=str(base_row.get("razao_social", "")))
                manual_fantasia = m1.text_input("Nome fantasia", value=str(base_row.get("nome_fantasia", "")))
                manual_apelido = m2.text_input("Apelido", value=str(base_row.get("apelido", "")))
                manual_regime = m1.selectbox("Regime", REGIMES, index=REGIMES.index(_regime_option(base_row.get("regime", REGIMES[0]))) if _regime_option(base_row.get("regime", REGIMES[0])) in REGIMES else 0)
                manual_cidade = m2.text_input("Cidade", value=str(base_row.get("cidade", "")))
                manual_uf = m1.text_input("UF", value=str(base_row.get("uf", "")), max_chars=2)
                manual_abertura = m2.text_input("Abertura", value=str(base_row.get("abertura", "")))
                manual_situacao = m1.text_input("Situação", value=str(base_row.get("situacao", "")))
                manual_porte = m2.text_input("Porte", value=str(base_row.get("porte", "")))
                manual_natureza = m1.text_input("Natureza jurídica", value=str(base_row.get("natureza_juridica", "")))
                manual_capital = m2.text_input("Capital social", value=str(base_row.get("capital_social", "")))
                manual_simples = m1.checkbox("Simples optante", value=int(base_row.get("simples_optante", 0) or 0) == 1)
                manual_mei = m2.checkbox("MEI optante", value=int(base_row.get("mei_optante", 0) or 0) == 1)
                manual_inativo = st.checkbox("Inativa", value=int(base_row.get("inativo", 0) or 0) == 1)
                b1, b2 = st.columns(2)
                submit_manual = b1.form_submit_button(f"{BUTTON_LABELS['salvar']} manualmente", type="primary")
                cancel_manual = b2.form_submit_button(BUTTON_LABELS["cancelar"], key="btn_cadastro_on_cancelar_manual")
            if cancel_manual:
                reset_empresa_cadastro_on_state()
                st.rerun()
            if submit_manual:
                manual_payload = {
                    "cnpj": manual_cnpj,
                    "razao_social": manual_razao,
                    "nome_fantasia": manual_fantasia,
                    "apelido": manual_apelido,
                    "regime": manual_regime,
                    "cidade": manual_cidade,
                    "uf": manual_uf,
                    "abertura": manual_abertura,
                    "situacao": manual_situacao,
                    "porte": manual_porte,
                    "natureza_juridica": manual_natureza,
                    "capital_social": manual_capital,
                    "simples_optante": 1 if manual_simples else 0,
                    "mei_optante": 1 if manual_mei else 0,
                    "inativo": 1 if manual_inativo else 0,
                }
                if len(cnpj_digits(manual_cnpj)) != 14:
                    st.error("CNPJ invalido. Informe 14 digitos.")
                elif not manual_razao.strip():
                    st.error("Razao social e obrigatoria.")
                else:
                    existing_id = int(st.session_state.get("empresa_cadastro_on_existing_id", 0) or 0)
                    save_empresa(manual_payload, existing_id or None)
                    st.session_state["empresa_save_notice"] = "Cadastro salvo manualmente."
                    reset_empresa_cadastro_on_state()
                    st.rerun()


def reset_empresa_cadastro_on_state() -> None:
    st.session_state["show_cadastro_on"] = False
    st.session_state["empresa_cadastro_on_mode"] = "lookup"
    st.session_state["empresa_cadastro_on_result"] = {}
    st.session_state["empresa_cadastro_on_error"] = ""
    st.session_state["empresa_cadastro_on_existing_id"] = 0
    st.session_state["empresa_cadastro_on_lookup_value"] = ""


def clear_empresa_cadastro_on_state() -> None:
    st.session_state["empresa_cadastro_on_mode"] = "lookup"
    st.session_state["empresa_cadastro_on_result"] = {}
    st.session_state["empresa_cadastro_on_error"] = ""
    st.session_state["empresa_cadastro_on_existing_id"] = 0
    st.session_state["empresa_cadastro_on_lookup_value"] = ""


def render_empresa_cadastro_on_panel() -> None:
    if not st.session_state.get("show_cadastro_on", False):
        return

    with st.container(border=True):
        head_left, head_right = st.columns([3, 1])
        head_left.markdown(
            "<h5 style='margin-top:0;margin-bottom:4px;'>Cadastro On / Incluir por CNPJ</h5>",
            unsafe_allow_html=True,
        )
        if head_right.button("❌ Fechar Cadastro On", use_container_width=True):
            reset_empresa_cadastro_on_state()
            st.rerun()

        st.caption("Digite o CNPJ, busque os dados e complete manualmente antes de salvar.")

        with st.form("form_cadastro_on_cnpj", clear_on_submit=False):
            lookup_value = st.text_input(
                "CNPJ",
                value=str(st.session_state.get("empresa_cadastro_on_lookup_value", "")),
                placeholder="Digite apenas números",
            )
            submitted_lookup = st.form_submit_button("🔎 Buscar dados")

        if submitted_lookup:
            digits = cnpj_digits(lookup_value)
            st.session_state["empresa_cadastro_on_lookup_value"] = digits
            if len(digits) != 14:
                st.session_state["empresa_cadastro_on_error"] = "CNPJ inválido. Informe 14 dígitos."
                st.session_state["empresa_cadastro_on_mode"] = "lookup"
                st.rerun()

            fetched = {}
            try:
                fetched = fetch_empresa_cadastro_on(digits)
            except Exception as exc:
                st.session_state["empresa_cadastro_on_error"] = str(exc) or "Falha ao buscar dados do CNPJ."

            existing = empresa_row_by_cnpj(normalize_cnpj(digits))
            if existing:
                st.warning("CNPJ já cadastrado.")
                st.session_state["empresa_cadastro_on_existing_id"] = int(existing.get("id", 0) or 0)
                base_row = {**existing, **fetched}
            else:
                st.session_state["empresa_cadastro_on_existing_id"] = 0
                base_row = fetched

            base_row["cnpj"] = normalize_cnpj(digits)
            st.session_state["empresa_cadastro_on_result"] = base_row
            st.session_state["empresa_cadastro_on_mode"] = "edit"
            st.rerun()

        if st.session_state.get("empresa_cadastro_on_error"):
            st.error(st.session_state["empresa_cadastro_on_error"])

        base_row = st.session_state.get("empresa_cadastro_on_result") or {}
        if st.session_state.get("empresa_cadastro_on_mode") == "edit":
            with st.container(border=True):
                st.markdown("#### Dados cadastrais")
                with st.form("form_cadastro_on_dados", clear_on_submit=False):
                    c1, c2 = st.columns(2)
                    cnpj = c1.text_input("CNPJ", value=str(base_row.get("cnpj", st.session_state.get("empresa_cadastro_on_lookup_value", ""))), disabled=True)
                    razao = c2.text_input("Razão social", value=str(base_row.get("razao_social", "")))
                    fantasia = c1.text_input("Nome fantasia", value=str(base_row.get("nome_fantasia", "")))
                    apelido = c2.text_input("Apelido", value=str(base_row.get("apelido", "")))
                    regime = c1.selectbox(
                        "Regime",
                        REGIMES,
                        index=REGIMES.index(_regime_option(base_row.get("regime", REGIMES[0]))) if _regime_option(base_row.get("regime", REGIMES[0])) in REGIMES else 0,
                    )
                    existing_id_for_regime = int(st.session_state.get("empresa_cadastro_on_existing_id", 0) or 0)
                    existing_regime = _regime_option(empresa_row(existing_id_for_regime).get("regime", "")) if existing_id_for_regime else ""
                    regime_vigencia = ""
                    if existing_regime and regime != existing_regime:
                        regime_vigencia = c2.date_input("Vigencia do regime").isoformat()
                    abertura = c2.text_input("Abertura", value=str(base_row.get("abertura", "")))
                    natureza_juridica = c1.text_input("Natureza jurídica", value=str(base_row.get("natureza_juridica", "")))
                    situacao = c2.text_input("Situação", value=str(base_row.get("situacao", "")))
                    capital_social = c1.text_input("Capital social", value=str(base_row.get("capital_social", "")))
                    porte = c2.text_input("Porte", value=str(base_row.get("porte", "")))
                    cidade = c1.text_input("Cidade", value=str(base_row.get("cidade", "")))
                    uf = c2.text_input("UF", value=str(base_row.get("uf", "")), max_chars=2)
                    simples_optante = c1.checkbox("Simples optante", value=int(base_row.get("simples_optante", 0) or 0) == 1)
                    mei_optante = c2.checkbox("MEI optante", value=int(base_row.get("mei_optante", 0) or 0) == 1)
                    mensalidade = c1.text_input("Mensalidade", value=str(base_row.get("mensalidade", "")))
                    inativo = c2.checkbox("Inativa", value=int(base_row.get("inativo", 0) or 0) == 1)

                    b1, b2, b3 = st.columns(3)
                    save_clicked = b1.form_submit_button("💾 Salvar cliente")
                    clear_clicked = b2.form_submit_button("🧹 Limpar")
                    cancel_clicked = b3.form_submit_button("❌ Cancelar")

                if clear_clicked:
                    clear_empresa_cadastro_on_state()
                    st.rerun()

                if cancel_clicked:
                    reset_empresa_cadastro_on_state()
                    st.rerun()

                if save_clicked:
                    if len(cnpj_digits(cnpj)) != 14:
                        st.error("CNPJ inválido. Informe 14 dígitos.")
                    elif not razao.strip():
                        st.error("Razão social é obrigatória.")
                    else:
                        payload = {
                            "cnpj": cnpj,
                            "razao_social": razao,
                            "nome_fantasia": fantasia,
                            "apelido": apelido,
                            "regime": regime,
                            "abertura": abertura,
                            "natureza_juridica": natureza_juridica,
                            "situacao": situacao,
                            "capital_social": capital_social,
                            "cidade": cidade,
                            "uf": uf,
                            "porte": porte,
                            "simples_optante": 1 if simples_optante else 0,
                            "mei_optante": 1 if mei_optante else 0,
                            "mensalidade": mensalidade,
                            "inativo": 1 if inativo else 0,
                            "regime_vigencia": regime_vigencia,
                        }
                        existing_id = int(st.session_state.get("empresa_cadastro_on_existing_id", 0) or 0)
                        if not existing_id:
                            existing_now = empresa_row_by_cnpj(normalize_cnpj(cnpj))
                            if existing_now:
                                existing_id = int(existing_now.get("id", 0) or 0)
                        save_empresa(payload, existing_id or None)
                        st.session_state["empresa_save_notice"] = "✅ Cliente salvo com sucesso"
                        st.toast("✅ Cliente salvo com sucesso")
                        reset_empresa_cadastro_on_state()
                        st.session_state["page"] = "Empresas"
                        st.query_params["page"] = "Empresas"
                        st.rerun()


def _selected_empresa_options(df: pd.DataFrame) -> list[int]:
    if df.empty or "id" not in df.columns:
        return []
    return [int(x) for x in df["id"].dropna().astype(int).tolist()]


def _empresa_option_label(empresa_id: int) -> str:
    row = empresa_row(int(empresa_id))
    if not row:
        return str(empresa_id)
    return f"{row.get('id')} - {row.get('apelido') or row.get('razao_social')} ({row.get('cnpj')})"


def _empresa_payload_from_form(
    *,
    cnpj: str,
    razao_social: str,
    nome_fantasia: str,
    apelido: str,
    regime: str,
    mensalidade: str,
    cidade: str,
    uf: str,
    funcionarios: bool,
    inativo: bool,
    abertura: str = "",
    natureza_juridica: str = "",
    situacao: str = "",
    capital_social: str = "",
    porte: str = "",
    simples_optante: bool = False,
    mei_optante: bool = False,
    link_rapido: str = "",
    senhas_acessos: str = "",
    observacoes: str = "",
    regime_vigencia: str = "",
) -> dict:
    return {
        "cnpj": cnpj,
        "razao_social": razao_social,
        "nome_fantasia": nome_fantasia,
        "apelido": apelido,
        "regime": regime,
        "mensalidade": mensalidade,
        "cidade": cidade,
        "uf": uf,
        "funcionarios": 1 if funcionarios else 0,
        "inativo": 1 if inativo else 0,
        "abertura": abertura,
        "natureza_juridica": natureza_juridica,
        "situacao": situacao,
        "capital_social": capital_social,
        "porte": porte,
        "simples_optante": 1 if simples_optante else 0,
        "mei_optante": 1 if mei_optante else 0,
        "link_rapido": link_rapido,
        "senhas_acessos": senhas_acessos,
        "observacoes": observacoes,
        "regime_vigencia": regime_vigencia,
    }


def apply_cadastro_on_to_editor_state(empresa_id: int, prefix: str) -> None:
    row = empresa_row(int(empresa_id))
    cnpj = row.get("cnpj", "") if row else ""
    if not cnpj_valido(cnpj):
        st.error("Empresa sem CNPJ valido para Cadastro On.")
        return
    try:
        info = fetch_empresa_cadastro_on(cnpj)
    except Exception as exc:
        st.error(f"Falha no Cadastro On: {exc}")
        return
    for key in [
        "cnpj",
        "razao_social",
        "nome_fantasia",
        "apelido",
        "regime",
        "abertura",
        "natureza_juridica",
        "situacao",
        "capital_social",
        "cidade",
        "uf",
        "porte",
        "simples_optante",
        "mei_optante",
    ]:
        st.session_state[f"{prefix}_{key}_{empresa_id}"] = info.get(key, "")
    st.toast("Dados do Cadastro On carregados para revisao.")


def render_empresa_quick_editor(empresa_id: int) -> None:
    row = empresa_row(int(empresa_id))
    if not row:
        st.warning("Empresa selecionada nao encontrada.")
        return

    with st.container(border=True):
        st.markdown("#### Edicao rapida")
        with st.form(f"empresa_quick_form_{empresa_id}", clear_on_submit=False):
            c1, c2, c3 = st.columns(3)
            cnpj = c1.text_input("CNPJ", value=str(row.get("cnpj", "")), key=f"quick_cnpj_{empresa_id}")
            razao = c2.text_input("Razao Social", value=str(row.get("razao_social", "")), key=f"quick_razao_social_{empresa_id}")
            fantasia = c3.text_input("Nome Fantasia", value=str(row.get("nome_fantasia", "")), key=f"quick_nome_fantasia_{empresa_id}")
            apelido = c1.text_input("Apelido", value=str(row.get("apelido", "")), key=f"quick_apelido_{empresa_id}")
            regime_before = _regime_option(row.get("regime", REGIMES[0]))
            regime = c2.selectbox("Regime", REGIMES, index=REGIMES.index(regime_before), key=f"quick_regime_{empresa_id}")
            mensalidade = c3.text_input("Mensalidade", value=str(row.get("mensalidade", "")), key=f"quick_mensalidade_{empresa_id}")
            cidade = c1.text_input("Cidade", value=str(row.get("cidade", "")), key=f"quick_cidade_{empresa_id}")
            uf = c2.text_input("UF", value=str(row.get("uf", "")), max_chars=2, key=f"quick_uf_{empresa_id}")
            funcionarios = c3.checkbox("Tem funcionarios", value=int(row.get("funcionarios", 0) or 0) == 1, key=f"quick_funcionarios_{empresa_id}")
            inativo = c1.checkbox("Inativo", value=int(row.get("inativo", 0) or 0) == 1, key=f"quick_inativo_{empresa_id}")
            regime_vigencia = ""
            if regime != regime_before:
                regime_vigencia = c2.date_input("Vigencia do regime").isoformat()
            b1, b2, b3, b4 = st.columns(4)
            save_clicked = b1.form_submit_button("Salvar")
            cadastro_on_clicked = b2.form_submit_button("Cadastro On")
            full_clicked = b3.form_submit_button("Editar completo")
            trash_clicked = b4.form_submit_button("Mover para lixeira")

        if cadastro_on_clicked:
            apply_cadastro_on_to_editor_state(empresa_id, "quick")
            st.rerun()
        if full_clicked:
            st.session_state["empresa_full_edit_id"] = int(empresa_id)
            st.rerun()
        if trash_clicked:
            move_empresa_to_trash(int(empresa_id))
            st.toast("Empresa movida para a lixeira.")
            st.session_state["empresa_quick_edit_id"] = 0
            st.rerun()
        if save_clicked:
            payload = _empresa_payload_from_form(
                cnpj=cnpj,
                razao_social=razao,
                nome_fantasia=fantasia,
                apelido=apelido,
                regime=regime,
                mensalidade=mensalidade,
                cidade=cidade,
                uf=uf,
                funcionarios=funcionarios,
                inativo=inativo,
                regime_vigencia=regime_vigencia,
            )
            save_empresa(payload, int(empresa_id))
            st.toast("Empresa atualizada.")
            st.rerun()


def render_editor_empresa(emp_id: int) -> None:
    row = empresa_row(int(emp_id))
    if not row:
        st.warning("Empresa selecionada nao encontrada.")
        return

    with st.container(border=True):
        st.markdown(f"#### Editor completo - {row.get('razao_social', '')}")
        regime_before = _regime_option(row.get("regime", REGIMES[0]))
        with st.form(f"empresa_full_form_{emp_id}", clear_on_submit=False):
            c1, c2, c3 = st.columns(3)
            cnpj = c1.text_input("CNPJ", value=str(row.get("cnpj", "")), key=f"full_cnpj_{emp_id}")
            razao = c2.text_input("Razao Social", value=str(row.get("razao_social", "")), key=f"full_razao_social_{emp_id}")
            fantasia = c3.text_input("Nome Fantasia", value=str(row.get("nome_fantasia", "")), key=f"full_nome_fantasia_{emp_id}")
            apelido = c1.text_input("Apelido", value=str(row.get("apelido", "")), key=f"full_apelido_{emp_id}")
            regime = c2.selectbox("Regime", REGIMES, index=REGIMES.index(regime_before), key=f"full_regime_{emp_id}")
            mensalidade = c3.text_input("Mensalidade", value=str(row.get("mensalidade", "")), key=f"full_mensalidade_{emp_id}")
            funcionarios = c1.checkbox("Tem funcionarios", value=int(row.get("funcionarios", 0) or 0) == 1, key=f"full_funcionarios_{emp_id}")
            abertura = c2.text_input("Abertura", value=str(row.get("abertura", "")), key=f"full_abertura_{emp_id}")
            natureza = c3.text_input("Natureza Juridica", value=str(row.get("natureza_juridica", "")), key=f"full_natureza_juridica_{emp_id}")
            situacao = c1.text_input("Situacao", value=str(row.get("situacao", "")), key=f"full_situacao_{emp_id}")
            capital = c2.text_input("Capital Social", value=str(row.get("capital_social", "")), key=f"full_capital_social_{emp_id}")
            cidade = c3.text_input("Cidade", value=str(row.get("cidade", "")), key=f"full_cidade_{emp_id}")
            uf = c1.text_input("UF", value=str(row.get("uf", "")), max_chars=2, key=f"full_uf_{emp_id}")
            porte = c2.text_input("Porte", value=str(row.get("porte", "")), key=f"full_porte_{emp_id}")
            simples = c1.checkbox("Simples Optante", value=int(row.get("simples_optante", 0) or 0) == 1, key=f"full_simples_optante_{emp_id}")
            mei = c2.checkbox("MEI Optante", value=int(row.get("mei_optante", 0) or 0) == 1, key=f"full_mei_optante_{emp_id}")
            inativo = c3.checkbox("Inativo", value=int(row.get("inativo", 0) or 0) == 1, key=f"full_inativo_{emp_id}")
            link_rapido = st.text_input("Link rapido", value=str(row.get("link_rapido", "")), key=f"full_link_rapido_{emp_id}")
            senhas = st.text_area("Senhas/Acessos", value=str(row.get("senhas_acessos", "")), key=f"full_senhas_acessos_{emp_id}")
            observacoes = st.text_area("Observacoes", value=str(row.get("observacoes", "")), key=f"full_observacoes_{emp_id}")
            regime_vigencia = ""
            if regime != regime_before:
                regime_vigencia = st.date_input("Data de vigencia do novo regime").isoformat()
            b1, b2, b3, b4, b5 = st.columns(5)
            save_clicked = b1.form_submit_button("Salvar")
            cadastro_on_clicked = b2.form_submit_button("Cadastro On")
            trash_clicked = b3.form_submit_button("Mover lixeira")
            back_clicked = b4.form_submit_button("Voltar")

        if cadastro_on_clicked:
            apply_cadastro_on_to_editor_state(emp_id, "full")
            st.rerun()
        if back_clicked:
            st.session_state["empresa_full_edit_id"] = 0
            st.rerun()
        if trash_clicked:
            move_empresa_to_trash(int(emp_id))
            st.toast("Empresa movida para a lixeira.")
            st.session_state["empresa_full_edit_id"] = 0
            st.rerun()
        if save_clicked:
            payload = _empresa_payload_from_form(
                cnpj=cnpj,
                razao_social=razao,
                nome_fantasia=fantasia,
                apelido=apelido,
                regime=regime,
                mensalidade=mensalidade,
                cidade=cidade,
                uf=uf,
                funcionarios=funcionarios,
                inativo=inativo,
                abertura=abertura,
                natureza_juridica=natureza,
                situacao=situacao,
                capital_social=capital,
                porte=porte,
                simples_optante=simples,
                mei_optante=mei,
                link_rapido=link_rapido,
                senhas_acessos=senhas,
                observacoes=observacoes,
                regime_vigencia=regime_vigencia,
            )
            save_empresa(payload, int(emp_id))
            st.toast("Empresa salva.")

            checked_tipos = []
            for tipo_code, label in DEMAND_TYPES:
                if st.session_state.get(f"demanda_vinc_{emp_id}_{tipo_code}", False):
                    checked_tipos.append(tipo_code)
            save_empresa_demandas(int(emp_id), checked_tipos)
            st.rerun()

        l1, l2, l3 = st.columns(3)
        l1.link_button("Abrir CNPJ.biz", cnpj_biz_url(row.get("cnpj", "")), use_container_width=True)
        l2.text_input("Copiar CNPJ", value=str(row.get("cnpj", "")), key=f"copy_cnpj_{emp_id}")
        l3.caption(f"Atualizado em: {row.get('atualizado_em', '')}")

        st.markdown("##### Acessos e compartilhamentos")
        current_contador = normalize_username(row.get("contador_responsavel", "DMLIMA")) or "DMLIMA"
        st.caption(f"Contador responsavel atual: {current_contador}")
        if is_admin_geral():
            contadores = all_contadores()
            novo_contador = st.selectbox(
                "Trocar contador responsavel",
                contadores,
                index=contadores.index(current_contador) if current_contador in contadores else 0,
                key=f"contador_resp_{emp_id}",
            )
            if st.button("Salvar contador responsavel", key=f"save_contador_resp_{emp_id}"):
                save_empresa({"contador_responsavel": novo_contador}, int(emp_id))
                execute(
                    "UPDATE demandas SET contador_responsavel=? WHERE empresa_id=? AND (contador_responsavel IS NULL OR contador_responsavel='' OR contador_responsavel=?)",
                    (normalize_username(novo_contador), int(emp_id), current_contador),
                )
                st.toast("Contador responsavel atualizado.")
                st.rerun()

        if can_share_cliente(int(emp_id)):
            contadores_destino = [c for c in all_contadores() if c != current_contador]
            with st.form(f"form_compartilhar_{emp_id}"):
                destino = st.selectbox("Compartilhar com contador", contadores_destino or [""], key=f"share_dest_{emp_id}")
                p1, p2, p3 = st.columns(3)
                pode_ver = p1.checkbox("Pode ver", value=True, key=f"share_ver_{emp_id}")
                pode_editar = p2.checkbox("Pode editar", value=False, key=f"share_editar_{emp_id}")
                pode_criar = p3.checkbox("Pode criar demandas", value=False, key=f"share_criar_{emp_id}")
                submit_share = st.form_submit_button("Salvar compartilhamento")
            if submit_share:
                salvar_compartilhamento_cliente(int(emp_id), destino, pode_ver, pode_editar, pode_criar, current_user())
                st.toast("Compartilhamento salvo.")
                st.rerun()

        compartilhamentos = load_cliente_compartilhamentos(int(emp_id))
        if not compartilhamentos.empty:
            show_table(
                compartilhamentos[["id", "contador_origem", "contador_destino", "pode_ver", "pode_editar", "pode_criar_demandas", "ativo"]],
                key=f"compart_{emp_id}",
                auto_height=True,
                row_height=28,
                editable=False,
            )
            if can_share_cliente(int(emp_id)):
                ativos = compartilhamentos[compartilhamentos["ativo"].astype(int) == 1]
                if not ativos.empty:
                    remove_id = st.selectbox("Remover compartilhamento", ativos["id"].astype(int).tolist(), format_func=lambda cid: f"#{cid}")
                    if st.button("Remover compartilhamento selecionado", key=f"remove_share_{emp_id}"):
                        remover_compartilhamento_cliente(int(remove_id), current_user())
                        st.toast("Compartilhamento removido.")
                        st.rerun()

        st.markdown("##### Estagiarios vinculados")
        if can_share_cliente(int(emp_id)):
            estagiarios = all_estagiarios()
            with st.form(f"form_estagiario_{emp_id}"):
                estagiario = st.selectbox("Estagiario", estagiarios or [""], key=f"estag_dest_{emp_id}")
                e1, e2, e3, e4 = st.columns(4)
                ver_cliente = e1.checkbox("Ver cliente", value=True, key=f"estag_ver_cli_{emp_id}")
                ver_demandas = e2.checkbox("Ver demandas", value=True, key=f"estag_ver_dem_{emp_id}")
                concluir_dem = e3.checkbox("Concluir demandas", value=True, key=f"estag_concluir_{emp_id}")
                comentar = e4.checkbox("Comentar", value=True, key=f"estag_comentar_{emp_id}")
                submit_est = st.form_submit_button("Salvar vinculo")
            if submit_est:
                salvar_estagiario_cliente(int(emp_id), estagiario, ver_cliente, ver_demandas, concluir_dem, comentar, current_user())
                st.toast("Estagiario vinculado.")
                st.rerun()
        estagiarios_df = load_cliente_estagiarios(int(emp_id))
        if not estagiarios_df.empty:
            show_table(
                estagiarios_df[["id", "estagiario_username", "pode_ver_cliente", "pode_ver_demandas", "pode_concluir_demandas", "pode_comentar", "ativo"]],
                key=f"estagiarios_{emp_id}",
                auto_height=True,
                row_height=28,
                editable=False,
            )
            if can_share_cliente(int(emp_id)):
                ativos_est = estagiarios_df[estagiarios_df["ativo"].astype(int) == 1]
                if not ativos_est.empty:
                    remove_est_id = st.selectbox("Remover estagiario", ativos_est["id"].astype(int).tolist(), format_func=lambda cid: f"#{cid}")
                    if st.button("Remover estagiario selecionado", key=f"remove_estag_{emp_id}"):
                        remover_estagiario_cliente(int(remove_est_id), current_user())
                        st.toast("Vinculo removido.")
                        st.rerun()

        st.markdown("##### Demandas vinculadas")
        selected_tipos = load_empresa_demandas(int(emp_id))
        cols = st.columns(3)
        for idx, (tipo_code, label) in enumerate(DEMAND_TYPES):
            with cols[idx % 3]:
                st.checkbox(label, value=tipo_code in selected_tipos, key=f"demanda_vinc_{emp_id}_{tipo_code}")
        if st.button("Salvar demandas vinculadas", key=f"save_demandas_vinc_{emp_id}", type="primary"):
            checked_tipos = [
                tipo_code for tipo_code, _ in DEMAND_TYPES
                if st.session_state.get(f"demanda_vinc_{emp_id}_{tipo_code}", False)
            ]
            save_empresa_demandas(int(emp_id), checked_tipos)
            st.toast("Demandas vinculadas salvas.")
            st.rerun()

        hist = load_historico_regime(int(emp_id))
        if not hist.empty:
            st.markdown("##### Historico de regime")
            show_table(hist, key=f"hist_regime_{emp_id}", auto_height=True, row_height=28, editable=False, disabled=True)


def render_empresas() -> None:
    st.markdown("**Empresas**")
    if is_estagiario():
        st.caption("Voce visualiza apenas clientes vinculados ao seu usuario.")

    if msg := st.session_state.pop("empresa_save_notice", None):
        st.toast(msg, icon="✅")

    if "empresa_selected_id" not in st.session_state:
        st.session_state["empresa_selected_id"] = 0
    if "empresa_quick_edit_id" not in st.session_state:
        st.session_state["empresa_quick_edit_id"] = 0
    if "empresa_full_edit_id" not in st.session_state:
        st.session_state["empresa_full_edit_id"] = 0
    if "empresas_view_mode" not in st.session_state:
        st.session_state["empresas_view_mode"] = "ativas"
    if "show_import_uploader" not in st.session_state:
        st.session_state["show_import_uploader"] = False
    if "show_cadastro_on" not in st.session_state:
        st.session_state["show_cadastro_on"] = False
    if "empresa_cadastro_on_mode" not in st.session_state:
        st.session_state["empresa_cadastro_on_mode"] = "lookup"
    if "empresa_cadastro_on_result" not in st.session_state:
        st.session_state["empresa_cadastro_on_result"] = {}
    if "empresa_cadastro_on_error" not in st.session_state:
        st.session_state["empresa_cadastro_on_error"] = ""
    if "empresa_cadastro_on_existing_id" not in st.session_state:
        st.session_state["empresa_cadastro_on_existing_id"] = 0
    if "empresa_cadastro_on_lookup_value" not in st.session_state:
        st.session_state["empresa_cadastro_on_lookup_value"] = ""

    inject_scroll_keeper("empresas")

    with st.container(border=True):
        c1, c2, cscope, c3, c4, c5, c6, c7 = st.columns([1.6, 1.0, 1.1, 1.2, 0.7, 0.8, 0.8, 0.8])
        search = c1.text_input(BUTTON_LABELS["buscar"], value=st.session_state.get("empresa_search", ""), label_visibility="collapsed", placeholder=BUTTON_LABELS["buscar"])
        st.session_state["empresa_search"] = search
        regime_filter = c2.selectbox("Regime", ["📋 Todos", *REGIMES], index=0, label_visibility="collapsed")
        if is_admin_geral():
            scope_options = ["Todos", "Meus clientes", "Compartilhados comigo"]
        elif is_contador():
            scope_options = ["Meus clientes", "Compartilhados comigo"]
        else:
            scope_options = ["Vinculados a mim"]
        scope_filter = cscope.selectbox("Escopo", scope_options, index=0, label_visibility="collapsed")

        empresas = load_empresas(active_only=False)
        filtered = empresas.copy()
        username = current_username()
        if scope_filter == "Meus clientes":
            filtered = filtered[filtered["contador_responsavel"].astype(str).str.upper() == username]
        elif scope_filter == "Compartilhados comigo":
            shared_ids = query_df(
                """
                SELECT empresa_id
                  FROM cliente_compartilhamentos
                 WHERE UPPER(contador_destino)=UPPER(?)
                   AND COALESCE(ativo,1)=1
                   AND COALESCE(pode_ver,1)=1
                """,
                (username,),
            )
            ids = set(shared_ids["empresa_id"].astype(int).tolist()) if not shared_ids.empty else set()
            filtered = filtered[filtered["id"].astype(int).isin(ids)] if ids else filtered.iloc[0:0]
        if search:
            q = search.strip().lower()
            mask = (
                filtered["cnpj"].astype(str).str.lower().str.contains(q, na=False)
                | filtered["razao_social"].astype(str).str.lower().str.contains(q, na=False)
                | filtered["nome_fantasia"].astype(str).str.lower().str.contains(q, na=False)
                | filtered["apelido"].astype(str).str.lower().str.contains(q, na=False)
            )
            filtered = filtered[mask]
        if regime_filter != "📋 Todos":
            filtered = filtered[filtered["regime"] == regime_filter]
        if st.session_state["empresas_view_mode"] == "excluidas":
            filtered = filtered[filtered["is_ativo"] == 0]
        else:
            filtered = filtered[filtered["is_ativo"] == 1]

        display_cols = ["id", "cnpj", "razao_social", "nome_fantasia", "apelido", "regime", "contador_responsavel", "mensalidade", "cidade", "uf"]
        display_df = filtered[display_cols].copy() if not filtered.empty else filtered
        export_df = display_df if not display_df.empty else filtered

        if c3.button(BUTTON_LABELS["incluir_cnpj"], key="btn_empresas_incluir_cnpj", type="primary", use_container_width=True, disabled=is_estagiario()):
            st.session_state["show_cadastro_on"] = True
            st.session_state["empresa_cadastro_on_mode"] = "lookup"
            st.session_state["empresa_cadastro_on_error"] = ""
            st.rerun()
        if c4.button(BUTTON_LABELS["ativas"], key="btn_empresas_ativas", type="primary" if st.session_state["empresas_view_mode"] == "ativas" else "secondary", use_container_width=True):
            st.session_state["empresas_view_mode"] = "ativas"
            st.rerun()
        if c5.button(BUTTON_LABELS["excluidas"], key="btn_empresas_excluidas", type="primary" if st.session_state["empresas_view_mode"] == "excluidas" else "secondary", use_container_width=True):
            st.session_state["empresas_view_mode"] = "excluidas"
            st.rerun()
        if c6.button(BUTTON_LABELS["importar"], key="btn_empresas_importar", type="primary" if st.session_state.get("show_import_uploader", False) else "secondary", use_container_width=True):
            st.session_state["show_import_uploader"] = not st.session_state.get("show_import_uploader", False)
            st.rerun()
        c7.download_button(
            BUTTON_LABELS["exportar"],
            data=empresas_export_csv(export_df),
            file_name=f"empresas_export_{datetime.now():%Y%m%d_%H%M%S}.csv",
            mime="text/csv",
            use_container_width=True,
        )
        selected_options = _selected_empresa_options(display_df)
        if selected_options:
            a1, a2, a3, a4, a5 = st.columns([2.2, 0.8, 1.1, 1.1, 1.0])
            selected_id = a1.selectbox(
                "Empresa selecionada",
                selected_options,
                index=selected_options.index(int(st.session_state.get("empresa_selected_id") or selected_options[0]))
                if int(st.session_state.get("empresa_selected_id") or selected_options[0]) in selected_options else 0,
                format_func=_empresa_option_label,
                label_visibility="collapsed",
                key="empresa_selected_select",
            )
            st.session_state["empresa_selected_id"] = int(selected_id)
            if a2.button("Recarregar", key="btn_empresas_recarregar", use_container_width=True):
                st.rerun()
            if a3.button("Editar selecionada", key="btn_empresas_editar", type="primary", use_container_width=True):
                st.session_state["empresa_quick_edit_id"] = int(selected_id)
                st.rerun()
            if st.session_state["empresas_view_mode"] == "excluidas":
                if a4.button("Restaurar", key="btn_empresas_restaurar", use_container_width=True):
                    restore_empresa_from_trash(int(selected_id))
                    st.toast("Empresa restaurada.")
                    st.session_state["empresas_view_mode"] = "ativas"
                    st.rerun()
            else:
                if a4.button("Mover para lixeira", key="btn_empresas_lixeira", use_container_width=True):
                    move_empresa_to_trash(int(selected_id))
                    st.toast("Empresa movida para a lixeira.")
                    st.rerun()
            if a5.button("Editor completo", key="btn_empresas_editor_completo", use_container_width=True):
                st.session_state["empresa_full_edit_id"] = int(selected_id)
                st.rerun()

    editable_mode = st.session_state["empresas_view_mode"] != "excluidas"

    render_empresa_cadastro_on_panel()
    if int(st.session_state.get("empresa_quick_edit_id", 0) or 0):
        render_empresa_quick_editor(int(st.session_state["empresa_quick_edit_id"]))
    if int(st.session_state.get("empresa_full_edit_id", 0) or 0):
        render_editor_empresa(int(st.session_state["empresa_full_edit_id"]))

    if st.session_state.get("show_import_uploader", False):
        with st.container(border=True):
            st.markdown("<h5 style='margin-top: 0px; margin-bottom: 4px;'>Importar Empresas</h5>", unsafe_allow_html=True)
            st.caption("Faca upload de uma planilha Excel (.xlsx, .xls) ou arquivo CSV para cadastrar ou atualizar empresas em massa por ID ou CNPJ.")
            uploaded_import = st.file_uploader(
                "Upload de arquivo",
                type=["csv", "xlsx", "xls"],
                label_visibility="collapsed",
                key="empresas_import_uploader",
            )
            if uploaded_import is not None:
                import_hash = hash(uploaded_import.getvalue())
                if st.session_state.get("empresas_last_import_hash") != import_hash:
                    try:
                        imported_df = empresas_import_dataframe(uploaded_import)
                        updated, created = empresas_apply_import(imported_df)
                        st.session_state["empresas_last_import_hash"] = import_hash
                        st.session_state["empresa_save_notice"] = f"Importacao concluida. Atualizados: {updated}. Criados: {created}."
                        st.session_state["show_import_uploader"] = False
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Nao foi possivel importar o arquivo. Detalhe: {exc}")

    if filtered.empty:
        st.info("Nenhuma empresa encontrada.")
        return

    table_height = calc_empresas_table_height(len(display_df))
    edited_df = show_table(
        display_df,
        key="empresas_editor",
        height=table_height,
        auto_height=True,
        editable=editable_mode,
        disabled=["id", "contador_responsavel"],
        row_height=35,
        column_config={
            "id": st.column_config.NumberColumn("id", width=60),
            "cnpj": st.column_config.TextColumn("cnpj", width=130),
            "razao_social": st.column_config.TextColumn("razao_social", width=240),
            "nome_fantasia": st.column_config.TextColumn("nome_fantasia", width=140),
            "apelido": st.column_config.TextColumn("apelido", width=120),
            "regime": st.column_config.SelectboxColumn("Regime", options=REGIMES, width=120),
            "contador_responsavel": st.column_config.TextColumn("contador", width=120),
            "mensalidade": st.column_config.TextColumn("mensalidade", width=100),
            "cidade": st.column_config.TextColumn("cidade", width=100),
            "uf": st.column_config.TextColumn("uf", width=50),
        },
    )

    if editable_mode:
        try:
            changed = 0
            original = display_df.set_index("id")
            for _, edited_row in edited_df.iterrows():
                empresa_id = int(edited_row["id"])
                if empresa_id not in original.index:
                    continue
                orig_row = original.loc[empresa_id]
                payload = {
                    "cnpj": clean_cell(edited_row.get("cnpj", "")),
                    "razao_social": clean_cell(edited_row.get("razao_social", "")),
                    "nome_fantasia": clean_cell(edited_row.get("nome_fantasia", "")),
                    "apelido": clean_cell(edited_row.get("apelido", "")),
                    "regime": clean_cell(edited_row.get("regime", "")),
                    "mensalidade": clean_cell(edited_row.get("mensalidade", "")),
                    "cidade": clean_cell(edited_row.get("cidade", "")),
                    "uf": clean_cell(edited_row.get("uf", "")),
                }
                if any(payload[key] != clean_cell(orig_row[key]) for key in payload):
                    save_empresa(payload, empresa_id)
                    changed += 1
            if changed:
                st.toast(f"✅ Alterações salvas automaticamente. Registros atualizados: {changed}.", icon="✅")
                mark_restore_scroll("empresas")
        except Exception as exc:
            st.error(f"Nao foi possivel salvar as alteracoes. Detalhe: {exc}")
    else:
        st.caption("Exibindo somente empresas exclu?das.")

    restore_scroll_if_needed("empresas")

def clear_novo_cliente_cadastro_on_state() -> None:
    st.session_state["novo_cliente_on_lookup"] = ""
    st.session_state["novo_cliente_on_data"] = {}
    st.session_state["novo_cliente_on_error"] = ""


def render_novo_cliente() -> None:
    st.subheader("Novo cliente")
    st.caption("Preencha os campos abaixo para criar um novo cadastro.")
    if is_estagiario():
        st.warning("Seu perfil nao permite cadastrar cliente.")
        return

    if "novo_cliente_on_lookup" not in st.session_state:
        st.session_state["novo_cliente_on_lookup"] = ""
    if "novo_cliente_on_data" not in st.session_state:
        st.session_state["novo_cliente_on_data"] = {}
    if "novo_cliente_on_error" not in st.session_state:
        st.session_state["novo_cliente_on_error"] = ""

    with st.container(border=True):
        st.markdown("<h5 style='margin-top:0;margin-bottom:4px;'>Cadastro On</h5>", unsafe_allow_html=True)
        st.caption("Use o CNPJ para consultar os dados cadastrais e preencher o formul?rio manual antes de salvar.")
        c1, c2, c3 = st.columns([1.3, 0.7, 0.7])
        lookup_cnpj = c1.text_input("CNPJ", value=st.session_state.get("novo_cliente_on_lookup", ""), label_visibility="collapsed", placeholder="CNPJ")
        if c2.button(BUTTON_LABELS["cadastro_on"], key="btn_novo_cliente_cadastro_on", type="primary", use_container_width=True):
            digits = only_digits(lookup_cnpj)
            if not cnpj_valido(digits):
                st.session_state["novo_cliente_on_error"] = "Informe um CNPJ v?lido com 14 d?gitos."
            else:
                try:
                    info = fetch_empresa_cadastro_on(digits)
                    st.session_state["novo_cliente_on_lookup"] = digits
                    st.session_state["novo_cliente_on_data"] = info
                    st.session_state["novo_cliente_on_error"] = ""
                except Exception as exc:
                    st.session_state["novo_cliente_on_error"] = str(exc) or "A consulta online falhou. Tente novamente ou preencha manualmente."
                st.rerun()
        if c3.button(BUTTON_LABELS["limpar"], key="btn_novo_cliente_limpar", use_container_width=True):
            clear_novo_cliente_cadastro_on_state()
            st.rerun()
        if st.session_state.get("novo_cliente_on_error"):
            st.error(st.session_state["novo_cliente_on_error"])
        if st.session_state.get("novo_cliente_on_data"):
            info = st.session_state["novo_cliente_on_data"]
            st.info(f"Dados carregados de {info.get('source', 'consulta online')}.")

    prefill = st.session_state.get("novo_cliente_on_data") or {}

    with st.container(border=True):
        with st.form("novo_cliente_form"):
            c1, c2 = st.columns(2)
            cnpj = c1.text_input("CNPJ", value=_first_filled(prefill.get("cnpj"), st.session_state.get("novo_cliente_on_lookup", "")))
            razao = c2.text_input("Razao social", value=_first_filled(prefill.get("razao_social")))
            fantasia = c1.text_input("Nome fantasia", value=_first_filled(prefill.get("nome_fantasia")))
            apelido = c2.text_input("Apelido", value=_first_filled(prefill.get("apelido")))
            regime = c1.selectbox("Regime", REGIMES, index=REGIMES.index(_regime_option(prefill.get("regime", REGIMES[0]))) if _regime_option(prefill.get("regime", REGIMES[0])) in REGIMES else 0)
            abertura = c2.text_input("Abertura", value=_first_filled(prefill.get("abertura")))
            natureza_juridica = c1.text_input("Natureza juridica", value=_first_filled(prefill.get("natureza_juridica")))
            situacao = c2.text_input("Situacao", value=_first_filled(prefill.get("situacao")))
            capital_social = c1.text_input("Capital social", value=_first_filled(prefill.get("capital_social")))
            porte = c2.text_input("Porte", value=_first_filled(prefill.get("porte")))
            cidade = c1.text_input("Cidade", value=_first_filled(prefill.get("cidade")))
            uf = c2.text_input("UF", value=_first_filled(prefill.get("uf")), max_chars=2)
            simples_optante = c1.checkbox("Simples optante", value=int(prefill.get("simples_optante", 0) or 0) == 1)
            mei_optante = c2.checkbox("MEI optante", value=int(prefill.get("mei_optante", 0) or 0) == 1)
            mensalidade = c1.text_input("Mensalidade", value=_first_filled(prefill.get("mensalidade", "")))
            inativo = c2.checkbox("Inativa", value=int(prefill.get("inativo", 0) or 0) == 1)
            contador_responsavel = "DMLIMA"
            if is_admin_geral():
                contadores = all_contadores()
                contador_responsavel = c1.selectbox("Contador responsavel", contadores, index=contadores.index("DMLIMA") if "DMLIMA" in contadores else 0)
            elif is_contador():
                contador_responsavel = current_username()
                c1.text_input("Contador responsavel", value=contador_responsavel, disabled=True)
            csave, ccancel = st.columns(2)
            save_new = csave.form_submit_button(f"{BUTTON_LABELS['salvar']} novo")
            cancel_new = ccancel.form_submit_button(BUTTON_LABELS["voltar"])

        if cancel_new:
            clear_novo_cliente_cadastro_on_state()
            st.session_state["page"] = "Empresas"
            st.query_params["page"] = "Empresas"
            st.rerun()

        if save_new:
            if not cnpj or not razao:
                st.error("CNPJ e razao social sao obrigatorios.")
            else:
                try:
                    save_empresa(
                        {
                            "cnpj": cnpj,
                            "razao_social": razao,
                            "nome_fantasia": fantasia,
                            "apelido": apelido,
                            "regime": regime,
                            "abertura": abertura,
                            "natureza_juridica": natureza_juridica,
                            "situacao": situacao,
                            "capital_social": capital_social,
                            "cidade": cidade,
                            "uf": uf,
                            "porte": porte,
                            "simples_optante": 1 if simples_optante else 0,
                            "mei_optante": 1 if mei_optante else 0,
                            "mensalidade": mensalidade,
                            "inativo": inativo,
                            "contador_responsavel": contador_responsavel,
                        },
                        None,
                    )
                    st.success("Novo cliente salvo.")
                    clear_novo_cliente_cadastro_on_state()
                    st.session_state["page"] = "Empresas"
                    st.query_params["page"] = "Empresas"
                    st.rerun()
                except Exception as exc:
                    st.error(f"Nao foi possivel salvar o novo cliente. Detalhe: {exc}")


def render_demandas(competencia: str) -> None:
    st.markdown("### Controle de Demandas")
    st.caption("Checklist operacional mensal por empresa, competencia, responsavel e status.")
    st.session_state["page"] = "Demandas"
    st.query_params["page"] = "Demandas"

    ensure_demanda_tipos_padrao()
    empresas = load_empresas_ativas()
    tipos_df = load_demanda_tipos(True)
    tipo_options = ["Todos"] + tipos_df["nome_curto"].astype(str).tolist()
    tipo_label_map = {str(row["nome_curto"]): str(row["nome"]) for _, row in tipos_df.iterrows()}
    tipo_order = {str(row["nome_curto"]): int(row["ordem"] or 999) for _, row in tipos_df.iterrows()}

    if empresas.empty:
        st.info("Cadastre empresas ativas antes de gerar demandas.")
        return

    users_df = get_users_df()
    responsaveis = sorted(users_df[users_df["ativo"] == 1]["username"].astype(str).str.upper().unique().tolist()) if not users_df.empty else []
    if current_username() and current_username() not in responsaveis:
        responsaveis.append(current_username())

    shared_count = 0
    if is_contador() and current_username():
        shared_df = query_df(
            "SELECT COUNT(*) AS total FROM cliente_compartilhamentos WHERE UPPER(contador_destino)=UPPER(?) AND COALESCE(ativo,1)=1 AND COALESCE(pode_ver,1)=1",
            (current_username(),),
        )
        shared_count = int(shared_df.iloc[0]["total"] or 0) if not shared_df.empty else 0
    h1, h2, h3, h4 = st.columns([1, 1, 1, 1])
    h1.metric("Competencia", competencia)
    h2.metric("Banco", "Supabase PostgreSQL" if using_postgres() else "SQLite local")
    h3.metric("Empresas ativas", len(empresas))
    h4.metric("Compartilhados", shared_count)

    with st.container(border=True):
        f1, f2, f3, f4 = st.columns([1.1, 1.4, 1, 1])
        competencia_filtro = f1.text_input("Competencia", value=competencia, key="dem_competencia")
        busca = f2.text_input("Buscar empresa/CNPJ/apelido", key="dem_busca")
        tipo_filter = f3.selectbox(
            "Tipo",
            tipo_options,
            format_func=lambda code: "Todos" if code == "Todos" else tipo_label_map.get(code, code),
            key="dem_tipo_filter",
        )
        status_filter = f4.selectbox("Status", ["Todos", *DEMANDA_STATUS], format_func=lambda s: "Todos" if s == "Todos" else DEMANDA_STATUS_LABELS.get(s, s), key="dem_status_filter")

        f5, f6, f7, f8 = st.columns([1, 1, 1, 1])
        responsavel_filter = f5.selectbox("Responsavel operacional", ["Todos", *responsaveis], key="dem_responsavel_filter")
        prioridade_filter = f6.selectbox("Prioridade", ["Todos", *DEMANDA_PRIORIDADES], key="dem_prioridade_filter")
        regimes = ["Todos"] + sorted([r for r in empresas["regime"].fillna("").astype(str).unique().tolist() if r])
        regime_filter = f7.selectbox("Regime", regimes, key="dem_regime_filter")
        minhas_default = is_estagiario()
        minhas = f8.checkbox("Apenas minhas", value=bool(st.session_state.get("dem_minhas", minhas_default)), key="dem_minhas")
        c9, c10, c11, c12 = st.columns([1, 1, 1, 1])
        atrasadas = c9.checkbox("Mostrar atrasadas", key="dem_atrasadas")
        mostrar_concluidas = c10.checkbox("Mostrar concluidas/canceladas", value=True, key="dem_mostrar_concluidas")
        contadores_filtro = ["Todos"] + sorted([c for c in empresas["contador_responsavel"].fillna("").astype(str).str.upper().unique().tolist() if c])
        contador_filter = c11.selectbox("Contador", contadores_filtro, key="dem_contador_filter")
        liberada_filter = c12.selectbox("Liberacao", ["Todos", "Liberada", "Bloqueada"], key="dem_liberada_filter")

    filtros = {
        "busca": busca,
        "tipo": "" if tipo_filter == "Todos" else tipo_filter,
        "status": "" if status_filter == "Todos" else status_filter,
        "responsavel": "" if responsavel_filter == "Todos" else responsavel_filter,
        "contador_responsavel": "" if contador_filter == "Todos" else contador_filter,
        "prioridade": "" if prioridade_filter == "Todos" else prioridade_filter,
        "regime": "" if regime_filter == "Todos" else regime_filter,
        "liberada": "" if liberada_filter == "Todos" else liberada_filter,
        "minhas": minhas,
        "atrasadas": atrasadas,
        "mostrar_concluidas": mostrar_concluidas,
    }
    demandas = load_demandas(competencia_filtro, filtros)

    total = len(demandas)
    pendentes = int((demandas["status"] == "pendente").sum()) if not demandas.empty else 0
    andamento = int((demandas["status"] == "em_andamento").sum()) if not demandas.empty else 0
    aguardando = int(demandas["status"].isin(["aguardando_cliente", "aguardando_documento"]).sum()) if not demandas.empty else 0
    concluidas = int((demandas["status"] == "concluida").sum()) if not demandas.empty else 0
    atrasadas_count = int(demandas["atrasada"].sum()) if not demandas.empty else 0
    pct = (concluidas / total * 100) if total else 0
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Total", total)
    m2.metric("Pendentes", pendentes)
    m3.metric("Em andamento", andamento)
    m4.metric("Aguardando", aguardando)
    m5.metric("Concluidas", concluidas)
    m6.metric("% concluido", f"{pct:.0f}%")
    if atrasadas_count:
        st.warning(f"Demandas atrasadas: {atrasadas_count}")

    a1, a2, a3, a4, a5, a6 = st.columns([1.2, 1.3, 1.4, 1.2, 1, 1])
    if a1.button("Gerar demandas do mes", key="gerar_dem_mes", type="primary", disabled=not can_manage_demandas()):
        report = gerar_demandas_por_config(competencia_filtro, current_user())
        st.session_state["dem_report"] = report
        st.toast(f"Demandas criadas: {report['criadas']} | existentes: {report['existentes']}")
        st.rerun()
    if a2.button("Reconciliar configuracao", key="reconciliar_dem", disabled=not can_manage_demandas()):
        report = reconciliar_demandas_competencia_por_config(competencia_filtro, current_user())
        st.session_state["dem_report"] = report
        st.toast(f"Reconciliacao: {report['criadas']} criadas.")
        st.rerun()
    if a3.button("Propagar pendencias anteriores", key="propagar_dem", disabled=not can_manage_demandas()):
        origem = competencia_anterior(competencia_filtro)
        report = propagar_pendencias_para_competencia(origem, competencia_filtro, current_user())
        st.session_state["dem_report"] = report
        st.toast(f"Propagadas: {report['criadas']} | existentes: {report['existentes']}")
        st.rerun()
    if a4.button("Recarregar", key="reload_demandas"):
        st.rerun()
    a5.download_button(
        "Exportar",
        data=demandas_export_csv(demandas),
        file_name=f"demandas_{competencia_filtro}.csv",
        mime="text/csv",
        disabled=demandas.empty,
        key="export_demandas",
    )

    if st.session_state.get("dem_report"):
        with st.expander("Relatorio da ultima operacao", expanded=False):
            st.json(st.session_state["dem_report"])

    with st.expander("Criar demanda manual", expanded=False):
        with st.form("form_criar_demanda_manual"):
            c1, c2 = st.columns([1.2, 1])
            empresa_id = c1.selectbox(
                "Empresa",
                empresas["id"].astype(int).tolist(),
                format_func=lambda eid: empresas.loc[empresas["id"] == eid, "apelido"].iloc[0] or empresas.loc[empresas["id"] == eid, "razao_social"].iloc[0],
                key="manual_dem_empresa",
            )
            tipo_manual = c2.selectbox(
                "Tipo",
                tipos_df["nome_curto"].astype(str).tolist(),
                format_func=lambda code: tipo_label_map.get(code, code),
                key="manual_dem_tipo",
            )
            c3, c4, c5 = st.columns(3)
            resp_manual = c3.selectbox("Responsavel", ["", *responsaveis], key="manual_dem_resp")
            prioridade_manual = c4.selectbox("Prioridade", DEMANDA_PRIORIDADES, index=DEMANDA_PRIORIDADES.index("normal"), key="manual_dem_prio")
            data_limite_manual = c5.date_input("Data limite", value=None, key="manual_dem_data")
            obs_manual = st.text_area("Observacao", key="manual_dem_obs")
            submitted = st.form_submit_button("Criar demanda", disabled=not can_manage_demandas())
            if submitted:
                created = create_demanda(
                    int(empresa_id),
                    tipo_manual,
                    competencia_filtro,
                    "manual",
                    resp_manual,
                    prioridade_manual,
                    obs_manual,
                    data_limite_manual.isoformat() if data_limite_manual else "",
                )
                st.toast("Demanda criada." if created else "Demanda ja existia para esta competencia.")
                st.rerun()

    if demandas.empty:
        st.info("Sem demandas para os filtros atuais.")
    else:
        st.markdown("#### Acoes rapidas")
        demanda_ids_top = demandas["demanda_id"].astype(int).tolist()
        selected_top = st.selectbox(
            "Selecionar demanda para acao",
            demanda_ids_top,
            format_func=lambda did: (
                f"#{did} - "
                f"{demandas.loc[demandas['demanda_id'] == did, 'empresa'].iloc[0]} | "
                f"{demandas.loc[demandas['demanda_id'] == did, 'demanda'].iloc[0]}"
            ),
            key="demanda_selected_top_id",
        )
        top_row = demandas[demandas["demanda_id"] == int(selected_top)].iloc[0].to_dict()
        top_liberada = int_flag(top_row.get("liberada"), 1) == 1
        top_can_concluir = usuario_pode_concluir_demanda(current_user(), int(selected_top)) and top_liberada
        if not top_liberada:
            st.warning(str(top_row.get("motivo_bloqueio") or "Demanda bloqueada por dependencia."))
        q1, q2, q3, q4, q5, q6 = st.columns(6)
        if q1.button("Concluir", key=f"top_concluir_{selected_top}", disabled=not top_can_concluir):
            concluir_demanda(int(selected_top), current_user())
            st.toast("Demanda concluida.")
            st.rerun()
        if q2.button("Iniciar", key=f"top_iniciar_{selected_top}", disabled=not usuario_pode_ver_demanda(current_user(), int(selected_top))):
            update_demanda_status(int(selected_top), "em_andamento", current_user())
            st.toast("Demanda em andamento.")
            st.rerun()
        if q3.button("Aguardar cliente", key=f"top_aguardar_cliente_{selected_top}", disabled=not usuario_pode_ver_demanda(current_user(), int(selected_top))):
            update_demanda_status(int(selected_top), "aguardando_cliente", current_user())
            st.toast("Marcada como aguardando cliente.")
            st.rerun()
        if q4.button("Aguardar doc.", key=f"top_aguardar_doc_{selected_top}", disabled=not usuario_pode_ver_demanda(current_user(), int(selected_top))):
            update_demanda_status(int(selected_top), "aguardando_documento", current_user())
            st.toast("Marcada como aguardando documento.")
            st.rerun()
        if q5.button("Reabrir", key=f"top_reabrir_{selected_top}", disabled=not usuario_pode_concluir_demanda(current_user(), int(selected_top))):
            reabrir_demanda(int(selected_top), current_user())
            st.toast("Demanda reaberta.")
            st.rerun()
        if q6.button("Cancelar", key=f"top_cancelar_{selected_top}", disabled=not can_cancel_demanda()):
            delete_or_cancel_demanda(int(selected_top), current_user(), "Cancelada pela acao rapida.")
            st.toast("Demanda cancelada.")
            st.rerun()

        with st.expander("Editar responsavel, prioridade, prazo e observacao", expanded=False):
            with st.form(f"top_editar_demanda_{selected_top}"):
                t1, t2, t3 = st.columns(3)
                resp_top = t1.selectbox(
                    "Responsavel",
                    ["", *responsaveis],
                    index=(["", *responsaveis].index(str(top_row.get("responsavel") or "")) if str(top_row.get("responsavel") or "") in ["", *responsaveis] else 0),
                    key=f"top_edit_resp_{selected_top}",
                    disabled=not can_assign_demanda() and not is_estagiario(),
                )
                prio_top = t2.selectbox(
                    "Prioridade",
                    DEMANDA_PRIORIDADES,
                    index=DEMANDA_PRIORIDADES.index(str(top_row.get("prioridade") or "normal")) if str(top_row.get("prioridade") or "normal") in DEMANDA_PRIORIDADES else 1,
                    key=f"top_edit_prio_{selected_top}",
                )
                raw_top_limite = str(top_row.get("data_limite") or "").strip()
                try:
                    limite_top_default = date.fromisoformat(raw_top_limite) if raw_top_limite else None
                except Exception:
                    limite_top_default = None
                limite_top = t3.date_input("Data limite", value=limite_top_default, key=f"top_edit_limite_{selected_top}")
                obs_top = st.text_area("Observacao", value=str(top_row.get("observacao") or ""), key=f"top_edit_obs_{selected_top}")
                if st.form_submit_button("Salvar edicao rapida"):
                    update_demanda_campos(
                        int(selected_top),
                        responsavel=resp_top,
                        prioridade=prio_top,
                        data_limite=limite_top.isoformat() if limite_top else "",
                        observacao=obs_top,
                        usuario=current_user(),
                    )
                    st.toast("Demanda atualizada.")
                    st.rerun()

        table_df = demandas[[
            "demanda_id", "empresa", "cnpj", "regime", "contador_responsavel", "demanda",
            "status_label", "liberacao", "bloqueio", "responsavel_operacional", "prioridade",
            "data_limite", "observacao", "atualizado_em", "concluida_em", "concluida_por",
        ]].rename(columns={"demanda_id": "id", "status_label": "status", "responsavel_operacional": "responsavel"})
        show_table(
            table_df,
            key=f"demandas_operacionais_{competencia_filtro}_{tipo_filter}_{status_filter}_{responsavel_filter}_{prioridade_filter}_{regime_filter}_{contador_filter}_{liberada_filter}_{minhas}_{atrasadas}_{mostrar_concluidas}",
            editable=False,
            disabled=True,
            auto_height=True,
            row_height=28,
            max_height=50000,
            column_config={
                "id": st.column_config.NumberColumn("id", width=70),
                "empresa": st.column_config.TextColumn("Empresa", width=210),
                "cnpj": st.column_config.TextColumn("CNPJ", width=150),
                "regime": st.column_config.TextColumn("Regime", width=130),
                "contador_responsavel": st.column_config.TextColumn("Contador", width=110),
                "demanda": st.column_config.TextColumn("Demanda", width=250),
                "status": st.column_config.TextColumn("Status", width=150),
                "liberacao": st.column_config.TextColumn("Liberada", width=110),
                "bloqueio": st.column_config.TextColumn("Bloqueio", width=240),
                "responsavel": st.column_config.TextColumn("Responsavel", width=120),
                "prioridade": st.column_config.TextColumn("Prioridade", width=100),
                "data_limite": st.column_config.TextColumn("Data limite", width=110),
                "observacao": st.column_config.TextColumn("Observacao", width=300),
            },
        )

        st.markdown("#### Acoes da demanda selecionada")
        demanda_ids = demandas["demanda_id"].astype(int).tolist()
        selected_id = st.selectbox(
            "Selecionar demanda",
            demanda_ids,
            format_func=lambda did: (
                f"#{did} - "
                f"{demandas.loc[demandas['demanda_id'] == did, 'empresa'].iloc[0]} | "
                f"{demandas.loc[demandas['demanda_id'] == did, 'demanda'].iloc[0]}"
            ),
            key="demanda_selected_id",
        )
        selected_row = demandas[demandas["demanda_id"] == int(selected_id)].iloc[0].to_dict()
        selected_liberada = int_flag(selected_row.get("liberada"), 1) == 1
        selected_can_concluir = usuario_pode_concluir_demanda(current_user(), int(selected_id)) and selected_liberada

        b1, b2, b3, b4, b5, b6 = st.columns(6)
        if b1.button("Concluir", key=f"concluir_{selected_id}", disabled=not selected_can_concluir):
            concluir_demanda(int(selected_id), current_user())
            st.toast("Demanda concluida.")
            st.rerun()
        if b2.button("Iniciar", key=f"iniciar_{selected_id}", disabled=not usuario_pode_ver_demanda(current_user(), int(selected_id))):
            update_demanda_status(int(selected_id), "em_andamento", current_user())
            st.toast("Demanda em andamento.")
            st.rerun()
        if b3.button("Aguardar cliente", key=f"aguardar_cliente_{selected_id}", disabled=not usuario_pode_ver_demanda(current_user(), int(selected_id))):
            update_demanda_status(int(selected_id), "aguardando_cliente", current_user())
            st.toast("Marcada como aguardando cliente.")
            st.rerun()
        if b4.button("Aguardar documento", key=f"aguardar_doc_{selected_id}", disabled=not usuario_pode_ver_demanda(current_user(), int(selected_id))):
            update_demanda_status(int(selected_id), "aguardando_documento", current_user())
            st.toast("Marcada como aguardando documento.")
            st.rerun()
        if b5.button("Reabrir", key=f"reabrir_{selected_id}", disabled=not usuario_pode_concluir_demanda(current_user(), int(selected_id))):
            reabrir_demanda(int(selected_id), current_user())
            st.toast("Demanda reaberta.")
            st.rerun()
        if b6.button("Cancelar", key=f"cancelar_{selected_id}", disabled=not can_cancel_demanda()):
            st.session_state[f"cancelar_demanda_{selected_id}"] = True

        with st.form(f"editar_demanda_{selected_id}"):
            e1, e2, e3, e4 = st.columns(4)
            status_edit = e1.selectbox(
                "Status",
                DEMANDA_STATUS,
                index=DEMANDA_STATUS.index(str(selected_row.get("status") or "pendente")),
                format_func=lambda s: DEMANDA_STATUS_LABELS.get(s, s),
                key=f"edit_status_{selected_id}",
            )
            resp_edit = e2.selectbox(
                "Responsavel",
                ["", *responsaveis],
                index=(["", *responsaveis].index(str(selected_row.get("responsavel") or "")) if str(selected_row.get("responsavel") or "") in ["", *responsaveis] else 0),
                key=f"edit_resp_{selected_id}",
                disabled=not can_assign_demanda() and not is_estagiario(),
            )
            prio_edit = e3.selectbox(
                "Prioridade",
                DEMANDA_PRIORIDADES,
                index=DEMANDA_PRIORIDADES.index(str(selected_row.get("prioridade") or "normal")) if str(selected_row.get("prioridade") or "normal") in DEMANDA_PRIORIDADES else 1,
                key=f"edit_prio_{selected_id}",
            )
            raw_limite = str(selected_row.get("data_limite") or "").strip()
            try:
                limite_default = date.fromisoformat(raw_limite) if raw_limite else None
            except Exception:
                limite_default = None
            limite_edit = e4.date_input("Data limite", value=limite_default, key=f"edit_limite_{selected_id}")
            obs_edit = st.text_area("Observacao", value=str(selected_row.get("observacao") or ""), key=f"edit_obs_{selected_id}")
            salvar_dem = st.form_submit_button("Salvar alteracoes")
            if salvar_dem:
                update_demanda_campos(
                    int(selected_id),
                    responsavel=resp_edit,
                    prioridade=prio_edit,
                    data_limite=limite_edit.isoformat() if limite_edit else "",
                    observacao=obs_edit,
                    usuario=current_user(),
                )
                if status_edit != str(selected_row.get("status") or ""):
                    update_demanda_status(int(selected_id), status_edit, current_user(), obs_edit)
                st.toast("Demanda atualizada.")
                st.rerun()

        if st.session_state.get(f"cancelar_demanda_{selected_id}"):
            with st.form(f"form_cancelar_{selected_id}"):
                motivo = st.text_area("Motivo do cancelamento", key=f"motivo_cancel_{selected_id}")
                if st.form_submit_button("Confirmar cancelamento"):
                    delete_or_cancel_demanda(int(selected_id), current_user(), motivo)
                    st.session_state.pop(f"cancelar_demanda_{selected_id}", None)
                    st.toast("Demanda cancelada.")
                    st.rerun()

        cmt_col, anex_col = st.columns(2)
        with cmt_col.expander("Comentarios", expanded=False):
            comentarios = load_demanda_comentarios(int(selected_id))
            if not comentarios.empty:
                show_table(comentarios, key=f"comentarios_{selected_id}", height=220, editable=False)
            novo_comentario = st.text_area("Novo comentario", key=f"novo_comentario_{selected_id}")
            if st.button("Adicionar comentario", key=f"add_comentario_{selected_id}"):
                add_demanda_comentario(int(selected_id), novo_comentario, current_user())
                st.toast("Comentario registrado.")
                st.rerun()
        with anex_col.expander("Anexos/links", expanded=False):
            anexos = load_demanda_anexos(int(selected_id))
            if not anexos.empty:
                show_table(anexos, key=f"anexos_{selected_id}", height=220, editable=False)
            link_nome = st.text_input("Nome", key=f"link_nome_{selected_id}")
            link_url = st.text_input("URL", key=f"link_url_{selected_id}")
            link_tipo = st.text_input("Tipo", key=f"link_tipo_{selected_id}")
            if st.button("Salvar link", key=f"add_link_{selected_id}"):
                add_demanda_anexo(int(selected_id), link_nome, link_url, link_tipo, current_user())
                st.toast("Link salvo.")
                st.rerun()

        with st.expander("Historico de status", expanded=False):
            hist = load_demanda_status_history(int(selected_id))
            if hist.empty:
                st.caption("Sem historico registrado.")
            else:
                show_table(hist, key=f"hist_dem_{selected_id}", height=260, editable=False)

    with st.expander("Configurar demandas por empresa", expanded=False):
        cfg_empresa_id = st.selectbox(
            "Empresa",
            empresas["id"].astype(int).tolist(),
            format_func=lambda eid: f"{empresas.loc[empresas['id'] == eid, 'apelido'].iloc[0] or empresas.loc[empresas['id'] == eid, 'razao_social'].iloc[0]} | {empresas.loc[empresas['id'] == eid, 'cnpj'].iloc[0]}",
            key="cfg_dem_empresa_id",
        )
        emp_cfg = empresas[empresas["id"] == int(cfg_empresa_id)].iloc[0].to_dict()
        st.caption(
            f"{emp_cfg.get('razao_social','')} | Regime: {emp_cfg.get('regime','')} | Cidade: {emp_cfg.get('cidade','')} | Funcionarios: {'sim' if int(emp_cfg.get('funcionarios',0) or 0) else 'nao'}"
        )
        current_config = load_config_demandas_empresa(int(cfg_empresa_id))
        cfg_prefix = f"cfg_dem_{cfg_empresa_id}"
        c1, c2, c3 = st.columns(3)
        if c1.button("Marcar padrao por regime", key=f"{cfg_prefix}_padrao", disabled=not can_config_demandas()):
            padrao = aplicar_regras_inteligentes_demanda(emp_cfg, set())
            for code in tipos_df["nome_curto"].astype(str).tolist():
                st.session_state[f"{cfg_prefix}_{code}"] = code in padrao
            st.rerun()
        if c2.button("Limpar", key=f"{cfg_prefix}_limpar", disabled=not can_config_demandas()):
            for code in tipos_df["nome_curto"].astype(str).tolist():
                st.session_state[f"{cfg_prefix}_{code}"] = False
            st.rerun()
        checked = []
        cols = st.columns(2)
        for idx, row in tipos_df.iterrows():
            code = str(row["nome_curto"])
            with cols[idx % 2]:
                if st.checkbox(str(row["nome"]), value=code in current_config, key=f"{cfg_prefix}_{code}"):
                    checked.append(code)
        s1, s2 = st.columns([1, 1])
        if s1.button("Salvar configuracao", key=f"{cfg_prefix}_salvar", type="primary", disabled=not can_config_demandas()):
            save_config_demandas_empresa(int(cfg_empresa_id), checked, current_user())
            st.toast("Configuracao salva.")
            st.rerun()
        if s2.button("Gerar/reconciliar competencia atual", key=f"{cfg_prefix}_gerar", disabled=not can_manage_demandas()):
            report = reconciliar_demandas_competencia_por_config(competencia_filtro, current_user())
            st.session_state["dem_report"] = report
            st.toast(f"Processado: {report['criadas']} criadas.")
            st.rerun()

    with st.expander("Visao matriz empresa x demanda", expanded=False):
        matriz_base = load_demandas(competencia_filtro, {"mostrar_concluidas": True})
        if matriz_base.empty:
            st.caption("Sem demandas para montar matriz.")
        else:
            symbol = {
                "pendente": "P",
                "em_andamento": "A",
                "aguardando_cliente": "!",
                "aguardando_documento": "!",
                "concluida": "C",
                "dispensada": "D",
                "cancelada": "X",
            }
            matriz_base["sinal"] = matriz_base.apply(lambda row: "!" if row.get("atrasada") else symbol.get(str(row.get("status")), ""), axis=1)
            matriz = matriz_base.pivot_table(index="empresa", columns="demanda", values="sinal", aggfunc="first", fill_value="")
            ordered_cols = sorted(matriz.columns, key=lambda label: tipo_order.get(next((c for c, l in DEMAND_LABELS.items() if l == label), ""), 999))
            show_table(matriz.reset_index()[["empresa", *ordered_cols]], key=f"matriz_dem_{competencia_filtro}", editable=False, auto_height=True, row_height=28, max_height=50000)

    with st.expander("Demandas por responsavel e relatorios rapidos", expanded=False):
        if demandas.empty:
            st.caption("Sem dados nos filtros atuais.")
        else:
            col1, col2 = st.columns(2)
            with col1:
                resp_count = demandas.groupby(["responsavel", "status"]).size().reset_index(name="qtd")
                show_table(resp_count, key=f"resp_count_{competencia_filtro}", height=280, editable=False)
            with col2:
                tipo_count = demandas.groupby(["demanda", "status"]).size().reset_index(name="qtd")
                show_table(tipo_count, key=f"tipo_count_{competencia_filtro}", height=280, editable=False)
            sem_config = []
            for _, emp in empresas.iterrows():
                if not load_config_demandas_empresa(int(emp["id"])):
                    sem_config.append({"empresa": emp.get("apelido") or emp.get("razao_social"), "cnpj": emp.get("cnpj"), "regime": emp.get("regime")})
            if sem_config:
                st.caption("Clientes ativos sem configuracao de demandas")
                show_table(pd.DataFrame(sem_config), key="empresas_sem_config_dem", height=260, editable=False)

    with st.expander("Ordenar tipos de demanda", expanded=False):
        if not can_config_demandas():
            st.info("Seu perfil nao permite alterar a ordem dos tipos.")
        else:
            order_df = tipos_df[["id", "codigo", "nome", "nome_curto", "ordem", "ativo"]].copy()
            edited_order = show_table(
                order_df,
                key="ordem_tipos_demanda",
                editable=True,
                disabled=["id", "codigo", "nome", "nome_curto"],
                height=520,
                column_config={
                    "ordem": st.column_config.NumberColumn("Ordem", width=90),
                    "ativo": st.column_config.CheckboxColumn("Ativo", width=80),
                },
            )
            o1, o2 = st.columns(2)
            if o1.button("Salvar ordem", key="salvar_ordem_demanda"):
                for _, row in edited_order.iterrows():
                    execute(
                        "UPDATE demanda_tipos SET ordem=?, ativo=?, atualizado_em=? WHERE id=?",
                        (int(row["ordem"] or 999), int(row["ativo"] or 0), now_str(), int(row["id"])),
                    )
                st.toast("Ordem salva.")
                st.rerun()
            if o2.button("Restaurar ordem padrao", key="restaurar_ordem_demanda"):
                for row in DEMAND_TYPE_ROWS:
                    execute(
                        "UPDATE demanda_tipos SET ordem=?, ativo=1, atualizado_em=? WHERE nome_curto=?",
                        (int(row["ordem"]), now_str(), str(row["nome_curto"])),
                    )
                st.toast("Ordem padrao restaurada.")
                st.rerun()

def render_automacao() -> None:
    st.subheader("Automacao")
    st.caption("Painel com acoes fiscais rapidas e atalhos para rotinas operacionais.")

    actions = [
        ("Baixar Guias do MEI", "Use a extensao: Baixar Guias_DMLS!"),
        ("Baixar NFe (Portal do Contribuinte)", "Rotina depende das credenciais e do fluxo do Portal do Contribuinte. A versao web sera ligada ao mesmo cadastro de acessos."),
        ("Extrair XML", "Use a extensao: Extrator XML (dmls)."),
        ("Analisar XML", "Selecione os XMLs na versao web para gerar uma analise simplificada."),
        ("Emitir Certidao Negativa", "Funcao em preparacao para integracao web."),
        ("Importar Pendencias", "Funcao em preparacao para integracao web."),
        ("Relatorio Fiscal", "Funcao em preparacao para integracao web."),
    ]

    for start in range(0, len(actions), 2):
        cols = st.columns(2)
        for idx, (label, message) in enumerate(actions[start:start + 2]):
            with cols[idx]:
                if st.button(label, key=f"auto_{label}"):
                    st.session_state["automacao_msg"] = message

    if st.session_state.get("automacao_msg"):
        st.info(st.session_state["automacao_msg"])

    with st.expander("Analisar XML na web", expanded=False):
        files = st.file_uploader("Selecionar XMLs", type=["xml"], accept_multiple_files=True)
        if files:
            rows = []
            for file in files:
                data = file.getvalue()
                rows.append({"arquivo": file.name, "tamanho_bytes": len(data)})
            show_table(
                pd.DataFrame(rows),
                key=f"leitura_fiscal_{len(rows)}",
                height=240,
                editable=False,
                disabled=True,
                column_config={
                    "arquivo": st.column_config.TextColumn("Arquivo", width=260),
                    "tamanho_bytes": st.column_config.NumberColumn("Tamanho (bytes)", width=140),
                },
            )
            st.warning("Leitura fiscal detalhada sera conectada na proxima etapa para espelhar o relatorio do desktop.")


def render_faturamento(competencia: str) -> None:
    st.subheader("Faturamento MEI")
    empresas = load_empresas(active_only=True)
    mei = empresas[empresas["regime"].str.upper() == "MEI"] if not empresas.empty else empresas
    if mei.empty:
        st.info("Nenhuma empresa MEI ativa encontrada.")
        return

    rows = query_df(
        """
        SELECT f.id, f.empresa_id, e.razao_social, f.competencia, f.valor,
               COALESCE(f.valor_nota_fiscal,0) AS valor_nota_fiscal,
               COALESCE(f.valor_mov_extrato,0) AS valor_mov_extrato,
               COALESCE(f.observacao,'') AS observacao
          FROM faturamento_mei f
          JOIN empresas e ON e.id=f.empresa_id
         WHERE f.competencia=?
         ORDER BY e.razao_social COLLATE NOCASE
        """,
        (competencia,),
    )
    show_table(
        rows,
        key=f"faturamento_table_{competencia}",
        height=260,
        editable=False,
        disabled=True,
        column_config={
            "id": st.column_config.NumberColumn("id", width=60),
            "empresa_id": st.column_config.NumberColumn("empresa_id", width=90),
            "razao_social": st.column_config.TextColumn("Razao social", width=260),
            "competencia": st.column_config.TextColumn("Competencia", width=110),
            "valor": st.column_config.TextColumn("Valor", width=90),
            "valor_nota_fiscal": st.column_config.TextColumn("NF", width=90),
            "valor_mov_extrato": st.column_config.TextColumn("Extrato", width=90),
            "observacao": st.column_config.TextColumn("Observacao", width=220),
        },
    )

    with st.form("faturamento_form"):
        empresa_id = st.selectbox(
            "Empresa MEI",
            mei["id"].tolist(),
            format_func=lambda eid: mei.loc[mei["id"] == eid, "razao_social"].iloc[0],
        )
        c1, c2, c3 = st.columns(3)
        valor = c1.number_input("Valor bruto", min_value=0.0, step=100.0, format="%.2f")
        valor_nf = c2.number_input("Notas fiscais", min_value=0.0, step=100.0, format="%.2f")
        valor_ext = c3.number_input("Movimento extrato", min_value=0.0, step=100.0, format="%.2f")
        observacao = st.text_area("Observacao")
        submitted = st.form_submit_button("Salvar faturamento")
    if submitted:
        timestamp = now_str()
        execute(
            """
            INSERT INTO faturamento_mei
                (empresa_id, competencia, valor, valor_nota_fiscal, valor_mov_extrato,
                 observacao, criado_em, atualizado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(empresa_id, competencia) DO UPDATE SET
                valor=excluded.valor,
                valor_nota_fiscal=excluded.valor_nota_fiscal,
                valor_mov_extrato=excluded.valor_mov_extrato,
                observacao=excluded.observacao,
                atualizado_em=excluded.atualizado_em
            """,
            (empresa_id, competencia, valor, valor_nf, valor_ext, observacao, timestamp, timestamp),
        )
        st.success("Faturamento salvo.")
        st.rerun()


def render_backup() -> None:
    st.subheader("Backup e dados")
    st.write("Use esta tela para baixar uma copia dos dados ou substituir a base SQLite local.")

    if using_postgres():
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for table in [
                "empresas",
                "empresa_demandas",
                "demandas",
                "historico_empresas",
                "historico_regime",
                "faturamento_mei",
                "settings",
                "users",
                "logs_sistema",
            ]:
                df = query_df(f"SELECT * FROM {table}")
                zf.writestr(f"{table}.csv", df.to_csv(index=False).encode("utf-8-sig"))
        st.download_button(
            "Baixar backup CSV",
            data=buffer.getvalue(),
            file_name=f"controle_empresas_backup_{datetime.now():%Y%m%d_%H%M%S}.zip",
            mime="application/zip",
        )
        st.info("Em modo PostgreSQL, a substituicao direta por arquivo .db fica desativada.")
        return

    if DB_PATH.exists():
        st.download_button(
            "Baixar cnpjs.db",
            data=DB_PATH.read_bytes(),
            file_name=f"cnpjs_backup_{datetime.now():%Y%m%d_%H%M%S}.db",
            mime="application/octet-stream",
        )

    uploaded = st.file_uploader("Substituir banco por outro cnpjs.db", type=["db", "sqlite", "sqlite3"])
    if uploaded and st.button("Confirmar substituicao"):
        backup_path = DB_PATH.with_suffix(f".bak_{datetime.now():%Y%m%d_%H%M%S}.db")
        if DB_PATH.exists():
            shutil.copy2(DB_PATH, backup_path)
        DB_PATH.write_bytes(uploaded.getbuffer())
        st.success("Banco substituido. Recarregue a pagina.")


def render_sidebar_secure() -> tuple[str, str]:
    menu_map = dict(NAV_MENU)
    override_page = st.session_state.pop("_nav_override_page", None)
    requested_page = normalize_page(override_page or st.query_params.get("page", st.session_state.get("page", "Painel")) or "Painel")
    if requested_page not in set(menu_map.values()):
        requested_page = "Painel"
        st.query_params["page"] = "Painel"
        st.session_state["page"] = "Painel"
        st.session_state["page_label"] = "Home"

    requested_label = next((label for label, page in menu_map.items() if page == requested_page), "Home")
    menu_items = list(menu_map.keys())
    menu_index = menu_items.index(requested_label) if requested_label in menu_items else 0
    if st.session_state.get("menu_secure") != requested_label and "menu_secure" in st.session_state:
        del st.session_state["menu_secure"]

    with st.sidebar:
        render_company_logo(72)
        st.markdown(
            f"<div style='margin:0.08rem 0 0.03rem 0; line-height:1.05;'><strong>Usuario:</strong> {current_user_display_name()}</div>"
            f"<div style='margin:0 0 0.08rem 0; line-height:1; color:var(--nexus-muted); font-size:0.88rem;'>Perfil: {user_role_label(current_user_role())}</div>",
            unsafe_allow_html=True,
        )
        page_label = st.radio("Menu", menu_items, index=menu_index, key="menu_secure")
        page = menu_map[page_label]
        st.session_state["page_label"] = page_label
        st.session_state["page"] = page
        if st.query_params.get("page") != page:
            st.query_params["page"] = page

        saved_competencia = st.session_state.get("competencia") or st.session_state.get("ultima_competencia") or current_competencia()
        st.session_state["ultima_competencia"] = saved_competencia
        current_year, current_month = parse_competencia(saved_competencia)
        years = list(range(current_year - 5, current_year + 6))
        month_options = [f"{m:02d}" for m in range(1, 13)]
        y1, y2 = st.sidebar.columns(2)
        year = y1.selectbox("Ano", years, index=years.index(current_year), key="ano_secure")
        month = y2.selectbox("Mes", month_options, index=month_options.index(f"{current_month:02d}"), key="mes_secure")
        competencia = f"{int(year)}-{month}"
        st.session_state["competencia"] = competencia
        touch_active_session(page)
        active_now = load_active_sessions()
        st.caption(f"Online: {active_now['usuario'].nunique()} | Sessoes: {len(active_now)}")
        if st.button("🔄 Recarregar dados", use_container_width=True):
            try:
                load_web_data.clear()
            except Exception:
                pass
            st.rerun()
    return page, competencia


def render_painel(competencia: str) -> None:
    if not is_web_simple_mode():
        st.subheader("Painel")
        st.info("Modo legado habilitado. Use as telas principais para navegar.")
        return

    st.subheader("Home")
    cols = st.columns(2)
    if cols[0].button("Cadastro de Empresas", key="home_open_empresas_simple", use_container_width=True):
        navigate_to("Empresas")
    if cols[1].button("Controle de Demandas", key="home_open_demandas_simple", use_container_width=True, type="primary"):
        navigate_to("Demandas")
    return
    st.caption(f"Fonte de dados: {get_data_source_mode()}")
    empresas = load_empresas_from_source(active_only=False)
    demandas = load_demandas_from_source(competencia, {})
    user = normalize_username(current_username())
    role = current_user_role()
    minhas_df = demandas[
        demandas["responsavel_operacional"].fillna("").astype(str).str.upper().eq(user)
        | demandas["estagiario_responsavel"].fillna("").astype(str).str.upper().eq(user)
    ].copy() if not demandas.empty and user else demandas.iloc[0:0].copy()

    total = len(demandas)
    pendentes = int((demandas["status"] == "pendente").sum()) if not demandas.empty else 0
    concluidas = int((demandas["status"] == "concluida").sum()) if not demandas.empty else 0
    pct_geral = round(100 * concluidas / total, 0) if total else 0
    minhas_total = len(minhas_df)
    minhas_concluidas = int((minhas_df["status"] == "concluida").sum()) if not minhas_df.empty else 0
    pct_minha = round(100 * minhas_concluidas / minhas_total, 0) if minhas_total else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Competencia", competencia)
    c2.metric("Total", total)
    c3.metric("Pendentes", pendentes)
    c4.metric("Concluidas", concluidas)
    c5.metric("% Geral", f"{pct_geral:.0f}%")

    st.markdown("##### Modulos")
    module_cols = st.columns(2)
    for idx, item in enumerate(MODULES):
        with module_cols[idx % 2]:
            st.markdown(
                f"""
                <div style="border:1px solid rgba(148,163,184,.22); border-radius:12px; padding:12px 14px; margin-bottom:10px; background:rgba(255,255,255,.68);">
                    <div style="font-weight:800; margin-bottom:4px;">{item['title']}</div>
                    <div style="font-size:0.9rem; opacity:0.82; margin-bottom:8px;">{item['desc']}</div>
                    <div style="font-size:0.74rem; text-transform:uppercase; letter-spacing:0.04em;">{item['tag']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if item.get("enabled"):
                if st.button(f"Abrir {item['title']}", key=f"home_mod_{idx}", use_container_width=True):
                    target = str(item.get("page") or "Painel")
                    st.session_state["page"] = target
                    st.query_params["page"] = target
                    st.rerun()
            else:
                st.button("Em breve", key=f"home_mod_disabled_{idx}", use_container_width=True, disabled=True)

    if role == "estagiario":
        c6, c7, c8 = st.columns(3)
        c6.metric("Minhas demandas", minhas_total)
        c7.metric("Minhas concluidas", minhas_concluidas)
        c8.metric("% Individual", f"{pct_minha:.0f}%")
    else:
        grouped = demandas.groupby("responsavel_operacional").size().reset_index(name="qtd") if not demandas.empty else pd.DataFrame()
        st.markdown("##### Demandas por responsavel")
        if grouped.empty:
            st.caption("Sem dados.")
        else:
            st.dataframe(grouped, use_container_width=True, hide_index=True)

    b1, b2 = st.columns([1, 1])
    if b1.button("📋 Abrir Demandas", use_container_width=True, type="primary"):
        st.session_state["page"] = "Demandas"
        st.query_params["page"] = "Demandas"
        st.rerun()
    if role != "estagiario" and b2.button("🏢 Ver Empresas", use_container_width=True):
        st.session_state["page"] = "Empresas"
        st.query_params["page"] = "Empresas"
        st.rerun()


def render_empresas() -> None:
    if not is_web_simple_mode():
        render_module_locked("Empresas")
        return

    st.subheader("Empresas")
    empresas = load_empresas_from_source(active_only=True)
    if empresas.empty:
        st.info("Nenhuma empresa encontrada na base da Web.")
        return

    c1, c2, c3 = st.columns([1.4, 1, 1])
    busca = c1.text_input("Buscar", placeholder="CNPJ, apelido ou razao social")
    contador_filter = c2.selectbox("Responsavel", ["Todos", *sorted(empresas["contador_responsavel"].fillna("").astype(str).str.upper().unique().tolist())], index=0)
    ativo_filter = c3.selectbox("Status", ["Ativas", "Todas"], index=0)

    filtered = empresas.copy()
    if busca:
        q = busca.strip().upper()
        blob = (
            filtered["cnpj"].fillna("").astype(str)
            + " "
            + filtered["apelido"].fillna("").astype(str)
            + " "
            + filtered["razao_social"].fillna("").astype(str)
            + " "
            + filtered["nome_fantasia"].fillna("").astype(str)
        ).str.upper()
        filtered = filtered[blob.str.contains(q, regex=False)].copy()
    if contador_filter != "Todos":
        filtered = filtered[filtered["contador_responsavel"].fillna("").astype(str).str.upper() == contador_filter].copy()
    if ativo_filter == "Ativas":
        filtered = filtered[filtered["ativo"].astype(int) == 1].copy()

    cols = ["empresa_id", "cnpj", "apelido", "razao_social", "nome_fantasia", "regime", "cidade", "uf", "contador_responsavel", "ativo"]
    st.dataframe(filtered[cols], use_container_width=True, hide_index=True)
    st.caption("Cadastro e edicao completa ficam no Python principal.")


def render_demandas(competencia: str) -> None:
    if not is_web_simple_mode():
        render_module_locked("Demandas")
        return

    st.subheader("Controle de Demandas")
    st.caption("Estagiarios veem as demandas de todos, mas so marcam as proprias.")

    empresas = load_empresas_from_source(active_only=False)
    users_df = load_usuarios_from_source()
    responsaveis = sorted(
        set(
            list(users_df["username"].astype(str).str.upper().tolist()) if not users_df.empty else []
        )
    )
    if current_username() and current_username() not in responsaveis:
        responsaveis.append(current_username())

    f1, f2, f3, f4 = st.columns([1.05, 1.2, 1, 1])
    competencia_filtro = f1.text_input("Competencia", value=competencia, key="web_dem_comp")
    busca = f2.text_input("Buscar", placeholder="empresa, cnpj, tipo", key="web_dem_busca")
    status_filter = f3.selectbox("Status", ["Todos", *DEMANDA_STATUS], key="web_dem_status")
    resp_filter = f4.selectbox("Responsavel", ["Todos", *responsaveis], key="web_dem_resp")

    f5, f6, f7, f8 = st.columns([1, 1, 1, 1])
    empresa_options = ["Todas"] + sorted(set([str(v) for v in empresas["apelido"].fillna("").astype(str).tolist() if str(v).strip()]))
    empresa_filter = f5.selectbox("Empresa", empresa_options, key="web_dem_empresa")
    tipos_df = load_demandas_from_source(competencia_filtro, {})
    tipo_options = ["Todos"] + sorted([t for t in tipos_df["tipo_demanda"].fillna("").astype(str).unique().tolist() if t])
    tipo_filter = f6.selectbox("Tipo", tipo_options, key="web_dem_tipo")
    minhas = f7.checkbox("Mostrar so minhas", value=is_estagiario(), key="web_dem_minhas")
    mostrar_concluidas = f8.checkbox("Mostrar concluidas", value=True, key="web_dem_concluidas")

    filtros = {
        "busca": busca,
        "status": "" if status_filter == "Todos" else status_filter,
        "responsavel": "" if resp_filter == "Todos" else resp_filter,
        "empresa": "" if empresa_filter == "Todas" else empresa_filter,
        "tipo": "" if tipo_filter == "Todos" else tipo_filter,
        "minhas": minhas,
        "mostrar_concluidas": mostrar_concluidas,
    }
    demandas = load_demandas_from_source(competencia_filtro, filtros)

    total = len(demandas)
    pendentes = int((demandas["status"] == "pendente").sum()) if not demandas.empty else 0
    concluidas = int((demandas["status"] == "concluida").sum()) if not demandas.empty else 0
    pct = round(100 * concluidas / total, 0) if total else 0
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total", total)
    m2.metric("Pendentes", pendentes)
    m3.metric("Concluidas", concluidas)
    m4.metric("% concluido", f"{pct:.0f}%")

    if demandas.empty:
        st.info("Nenhuma demanda encontrada com os filtros atuais.")
        return

    view_cols = [
        "demanda_id", "empresa", "tipo_demanda", "responsavel_operacional",
        "estagiario_responsavel", "status", "data_limite", "bloqueada", "motivo_bloqueio",
        "observacao", "concluida_em", "concluida_por", "atualizado_em",
    ]
    st.dataframe(demandas[view_cols], use_container_width=True, hide_index=True)

    selected_id = st.selectbox(
        "Selecionar demanda",
        demandas["demanda_id"].astype(int).tolist(),
        format_func=lambda did: f"{int(did)} - {demandas.loc[demandas['demanda_id'].astype(int) == int(did), 'empresa'].iloc[0]} | {demandas.loc[demandas['demanda_id'].astype(int) == int(did), 'tipo_demanda'].iloc[0]}",
        key="web_dem_selected",
    )
    row = demandas.loc[demandas["demanda_id"].astype(int) == int(selected_id)].iloc[0].to_dict()
    locked = bool(int(row.get("bloqueada", 0) or 0))
    can_mark = can_user_mark_demanda(current_username(), row) and not locked
    st.markdown("##### Detalhes")
    cols = st.columns(3)
    cols[0].write(f"**Empresa:** {row.get('empresa', '')}")
    cols[1].write(f"**Responsavel:** {row.get('responsavel_operacional', '') or row.get('estagiario_responsavel', '')}")
    cols[2].write(f"**Status:** {row.get('status', '')}")
    if locked:
        st.warning(f"Bloqueada: {row.get('motivo_bloqueio', '')}")

    obs = st.text_area("Observacao curta", value=str(row.get("observacao", "")), key=f"web_obs_{selected_id}", height=90)
    a1, a2, a3, a4 = st.columns(4)
    if a1.button("✅ Concluir", disabled=not can_mark, use_container_width=True):
        save_demanda_status_to_source(int(selected_id), "concluida", obs, current_username())
        st.rerun()
    if a2.button("▶️ Em andamento", disabled=not can_mark, use_container_width=True):
        save_demanda_status_to_source(int(selected_id), "em_andamento", obs, current_username())
        st.rerun()
    if a3.button("📝 Salvar observacao", disabled=not can_mark, use_container_width=True):
        save_demanda_status_to_source(int(selected_id), str(row.get("status", "pendente")), obs, current_username())
        st.rerun()
    if a4.button("🔄 Atualizar", use_container_width=True):
        st.rerun()

    if not can_mark:
        st.caption("Somente a demanda atribuida ao seu usuario pode ser marcada.")


def main() -> None:
    st.set_page_config(page_title="Controle de Empresas", layout="wide", initial_sidebar_state="expanded")
    apply_nexus_theme()
    ensure_database_ready()

    if not require_login_secure():
        return

    render_topbar()
    st.title("Controle de Empresas")

    if not db_exists():
        render_setup()
        return

    page, competencia = render_sidebar_secure()

    if page == "Modulos":
        render_modulos()
    elif page == "Painel":
        render_painel(competencia)
    elif page == "Empresas":
        render_empresas()
    elif page == "Demandas":
        render_demandas(competencia)
    else:
        render_module_locked(page)


if __name__ == "__main__":
    main()


