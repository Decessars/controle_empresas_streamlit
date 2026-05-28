# Controle de Empresas - versão Streamlit

Esta pasta é uma versão web inicial do sistema `Controle Empresas_53.py`.

O aplicativo desktop original continua preservado. Esta versão usa Streamlit para rodar no navegador, localmente ou em nuvem.

A regra de evolução está em `PARIDADE_DESKTOP_WEB.md`: sempre que o desktop ganhar ou alterar uma função, a versão web deve receber a mesma função ou registrar o módulo como pendente/desabilitado.

## Modos de uso

Esta versão web tem dois modos:

- Offline/local: usa `data/cnpjs.db`, ideal para rodar no seu computador.
- Online/nuvem: usa PostgreSQL quando a variável ou secret `DATABASE_URL` estiver configurada.

Se não existir `DATABASE_URL`, o app usa SQLite automaticamente.

## Rodar localmente/offline

```powershell
cd "H:\Meu Drive\2026\Python Contabilidade\#21 Demandas Contabilidade\controle_empresas_streamlit"
py -m pip install -r requirements.txt
py -m streamlit run "Exelencia Contabilidade.py"
```

Depois acesse:

```text
http://localhost:8501
```

## Usar o banco atual

O banco local principal está em:

```text
..\_dados_app\cnpjs.db
```

Para copiar esse banco para a versão web:

```powershell
.\scripts\copiar_banco_local.ps1
```

Também é possível abrir o app e enviar o arquivo `cnpjs.db` pela tela inicial.

## Usar banco online PostgreSQL

Configure a URL do banco:

```powershell
set DATABASE_URL=postgresql+psycopg://usuario:senha@host:5432/banco
streamlit run "Exelencia Contabilidade.py"
```

Para migrar o `cnpjs.db` local para o PostgreSQL:

```powershell
set DATABASE_URL=postgresql+psycopg://usuario:senha@host:5432/banco
python scripts\migrar_sqlite_para_postgres.py --replace
```

O arquivo `Migrar banco para PostgreSQL.bat` faz a mesma chamada, desde que `DATABASE_URL` já esteja definida.

## Publicar online

1. Crie um repositório no GitHub com os arquivos desta pasta.
2. No Streamlit Community Cloud, selecione o repositório.
3. Use `Exelencia Contabilidade.py` como arquivo principal.
4. Cadastre usuários e senhas se for evoluir para acesso externo.

Para ativar senha no Streamlit Cloud, configure os secrets do app assim:

```toml
[auth.users]
admin = "sua-senha-forte"
funcionario = "outra-senha"

[database]
url = "postgresql+psycopg://usuario:senha@host:5432/banco"
```

Se nenhum usuario for configurado via `st.secrets` ou variaveis de ambiente, o app usa o arquivo versionado `usuarios_senhas.txt` como fallback para permitir o login na nuvem.

O app também mantém o arquivo `usuarios_senhas.txt` sincronizado com as credenciais carregadas.

Se não existir banco na nuvem, o app cria automaticamente um SQLite vazio na primeira execução. Os dados reais continuam dependendo da importação do `cnpjs.db` local ou de um PostgreSQL online.

## Atenção sobre dados reais

Não publique `data/cnpjs.db` em repositório público. Ele pode conter CNPJs, dados de clientes e credenciais.

Para uso real com vários funcionários, use PostgreSQL/Supabase ou outro banco online. SQLite funciona para teste e uso local, mas não é a melhor base para múltiplos usuários editando ao mesmo tempo em nuvem.

## Sincronização entre online e offline

Neste estágio, o sistema suporta os dois modos, mas eles não sincronizam automaticamente linha a linha.

Fluxos seguros:

- Local/offline: trabalhar no `data/cnpjs.db` e fazer backup pela tela `Backup`.
- Online: trabalhar no PostgreSQL, com usuários acessando a mesma base.
- Migração inicial: rodar `scripts\migrar_sqlite_para_postgres.py --replace` para enviar a base local para o banco online.

Sincronização automática bidirecional exige regra de conflito, histórico por alteração e controle de usuário. Isso pode ser criado em uma próxima etapa se você realmente precisar alternar edição offline e online no mesmo período.
