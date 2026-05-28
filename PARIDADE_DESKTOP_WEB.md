# Paridade Desktop/Web

Objetivo: manter a versão web em Streamlit sincronizada funcionalmente com o aplicativo desktop `Controle Empresas_53.py`.

Regras de manutenção:

- Toda nova função criada no desktop deve ser avaliada também na web.
- Se a função ainda não puder ser implementada na web, ela deve aparecer como `Em implantação` na tela `Módulos`.
- Botões e rotinas importantes do desktop devem ter equivalente web, ainda que o layout seja adaptado ao navegador.
- Alterações em banco de dados devem ser compatíveis com SQLite local e PostgreSQL online.
- Dados sensíveis nunca devem ser versionados no GitHub.

Status atual:

- Habilitado: Painel, Empresas, Demandas, Faturamento MEI e Backup.
- Em implantação: Configurações, Lixeira, Ordem das Demandas, Movimentador de Arquivos, Relatórios e Portal/Credenciais.
