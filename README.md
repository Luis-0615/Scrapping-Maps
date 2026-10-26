# Scrapping-Maps

Coleção de ferramentas de pesquisa e qualificação de leads, organizada por fonte.

## Projetos

- **[Google Maps (Maps Leads BR)](maps/LEIA-ME.md):** coleta de empresas por termos e cidades usando Docker; inclui listas de busca, cruzamento de CNPJs e análise de sites.
- **[LinkedIn (MCP)](linkedin/README.md):** consulta de empresas, profissionais por cargo e perfis, com exportação em CSV, XLSX e JSON.

## Começar

**Google Maps:** entre na pasta `maps/`, execute `docker compose up -d` e siga o guia [LEIA-ME.md](maps/LEIA-ME.md). Para análise e cruzamento dos dados, veja [Pós-processamento](maps/POS-PROCESSAMENTO.md).

**LinkedIn:** entre em `linkedin/` e siga o [guia de instalação e uso](linkedin/README.md).

Os scripts são executados localmente. Não versione resultados de scraping, credenciais, cookies, listas com dados pessoais ou arquivos de sessões. Respeite a privacidade, a LGPD e os termos das plataformas consultadas.
