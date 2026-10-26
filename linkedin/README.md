# Coletor LinkedIn via MCP

Ferramenta de linha de comando para consultar empresas e profissionais via servidor MCP do LinkedIn, **sem consumo do limite do Codex**. Derivada do script `scrapping_linkedin.py` fornecido pelo usuário.

## Pré-requisitos

- Python 3.11+ e Chrome no Windows.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) instalado, com o comando `uvx` acessível.
- Sessão autenticada no LinkedIn, no navegador local.
- Conexão com a internet.

Instalação no PowerShell:

```powershell
cd linkedin
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Se a detecção automática do Chrome falhar:

```powershell
$env:CHROME_PATH = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
```

## Usos

**Empresas do segmento de tecnologia em São Paulo**

```powershell
python scrapping_linkedin.py --pausa 5 empresas --segmento "tecnologia" --regiao "Sao Paulo" --limite 20
```

**Pessoas por cargo em uma empresa**

```powershell
python scrapping_linkedin.py --pausa 5 pessoas --empresa "https://www.linkedin.com/company/microsoft/" --cargo "diretor" --limite 10
```

**Leitura de URLs recebidas**

```powershell
python scrapping_linkedin.py links "https://www.linkedin.com/company/microsoft/" --limite 10
python scrapping_linkedin.py links --arquivo urls.txt --limite 10
```

No CSV, informe uma coluna `url`, `linkedin_url`, `linkedin`, `link` ou `perfil`. As URLs são normalizadas e duplicatas descartadas. `--contato` solicita a seção de contato dos perfis de pessoas; use somente com base legal e finalidade legítima.

## Resultados

A pasta `resultados_linkedin/` é criada no diretório de execução, com três arquivos por consulta:

| Formato | Conteúdo |
| --- | --- |
| CSV | Dados tabulares para planilhas, UTF-8 com BOM |
| XLSX | Mesmos dados em Excel |
| JSON | Resposta original do MCP, para diagnóstico |

Colunas: `tipo`, `nome_exibido`, `linkedin_url`, `funcionarios`, `empresa`, `cargo_pesquisado`, `consulta`, `status`, `texto_coletado`.

A coluna `funcionarios` é a **faixa de funcionários declarada pelo perfil da empresa**, não uma quantidade exata verificada. Profissionais retornados pela busca são candidatos não validados.

Limite de 1 a 50 resultados por execução e pausa padrão de 5 segundos entre chamadas. A flag `--pausa` deve anteceder o modo. Se houver erro de limite da plataforma, o script interrompe as consultas, sem contornar o bloqueio.

O MCP externo pode alterar parâmetros entre versões. **Os testes offline não comprovam funcionamento real com o LinkedIn**.

## Testes

```powershell
pip install -r requirements-dev.txt
python -m pytest -q tests
```

**Privacidade:** o JSON bruto pode conter dados pessoais. A pasta de resultados está no `.gitignore` e não deve ser versionada.
