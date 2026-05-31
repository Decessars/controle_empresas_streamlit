# Arquitetura Oficial do Projeto - Python Principal + Web Simples

## Visao Geral

- `Controle Empresas_54.py` e a fonte principal da logica do sistema.
- O sistema Web nao deve replicar toda a logica do Python.
- O Python e responsavel por cadastro completo de empresas, Cadastro On por CNPJ, configuracao de demandas, geracao de demandas mensais, regras por regime, regras por funcionarios, historico, rotinas administrativas e exportacao/espelhamento dos dados para a Web quando necessario.
- O sistema Web e responsavel apenas por login de usuarios, visualizacao de empresas, visualizacao de demandas, filtros simples, marcacao de demandas como concluidas, observacao curta e exibicao de percentuais e indicadores basicos.
- Cadastro de Empresas e Controle de Demandas sao os unicos modulos ativos inicialmente.
- Demais modulos devem ficar desativados ou apenas como visualizacao futura.
- Estagiarios nao cadastram clientes.
- O cadastro de clientes e feito principalmente por DMLIMA/contador no Python.
- Estagiarios veem as demandas de todos para ter panorama geral, mas so podem marcar as proprias demandas.
- A Web deve ser simples, objetiva, compacta e operacional.

## Fonte De Dados

- Prioridade atual: base local compartilhada gerada pelo Python.
- A Web deve ler os arquivos em `controle_empresas_streamlit/data_web`.
- O Python exporta a base em formato SQLite e CSV para consumo da Web.
- O modo `supabase` permanece opcional e futuro.

## Ciclo De Sincronizacao

1. O Python gera e exporta a base Web.
2. Os estagiarios usam a Web para consultar e marcar demandas.
3. A Web registra marcações simples.
4. O Python importa as marcações da Web.
5. O Python atualiza a base principal.
6. O Python exporta novamente a base Web.

## Modulos Ativos

- Home
- Cadastro de Empresas
- Controle de Demandas

## Modulos Desativados

- Automacao
- Faturamento
- Backup
- Relatorios avancados
- Usuarios, se nao for essencial na fase atual

## Regras De Demandas

- Estagiarios veem as demandas de todos.
- Estagiarios so podem marcar as demandas proprias.
- Admin e contador podem ver o panorama geral e acompanhar percentuais.
- Demandas bloqueadas ficam visiveis, mas sem acao de conclusao.

## Observacao Final

- O objetivo desta fase e simplificar a operacao da Web sem duplicar a logica administrativa do desktop.
