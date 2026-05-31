# Data Web

Esta pasta recebe a exportacao oficial gerada por `Controle Empresas_54.py` para alimentar o painel Streamlit.

Arquivos esperados:

- `empresas_web.csv`
- `demandas_web.csv`
- `usuarios_web.csv`
- `metadata_web.json`
- `marcacoes_web.csv` local, quando houver marcacoes feitas na Web

Regras:

- `empresas_web.csv`, `demandas_web.csv`, `usuarios_web.csv` e `metadata_web.json` sao a base leve de leitura da Web.
- `marcacoes_web.csv` registra acoes dos usuarios da Web e nao deve conter senhas.
- `usuarios_senhas.txt`, `.streamlit/secrets.toml` e dados sensiveis nao devem ser versionados.
- Se o repositorio for publico, nao suba dados reais de clientes.
- Se o repositorio for privado, ainda assim evite expor senhas, tokens e informacoes desnecessarias.
