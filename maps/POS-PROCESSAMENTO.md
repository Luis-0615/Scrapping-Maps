# Pós-processamento dos leads do Google Maps

O coletor principal `scrape_br.py` usa a biblioteca padrão do Python e não precisa de `pip install`. Já as etapas opcionais de cruzamento com a Receita e análise dos sites precisam de bibliotecas extras.

## Instalação

Execute na pasta `maps/`:

```bash
python -m pip install -r requirements.txt
```

## Etapa 3: cruzar Maps com Receita

```bash
python cruzar_maps.py leads.csv receita_enriquecida.csv leads_com_cnpj.csv
```

- `leads.csv`: saída gerada pelo coletor.
- `receita_enriquecida.csv`: base de Receita previamente tratada, **não incluída neste repositório**.
- `leads_com_cnpj.csv`: resultado com as informações de cruzamento.

O script espera colunas como `Município`, `Razão Social`, `Nome Fantasia`, `fone_norm`, `fone_qtd`, `num_end` e `cep8` na base enriquecida. Os cruzamentos usam telefone, CEP e número, ou similaridade de nome no município. São inferências de correspondência, não confirmação oficial de CNPJ.

## Etapa 4: analisar os sites das empresas

```bash
python checar_sites.py leads_com_cnpj.csv website leads_verificados.csv
```

O segundo argumento deve ser o nome da coluna de sites do CSV, geralmente `website`. O script identifica possíveis plataformas de e-commerce, carrinho, Instagram, links de marketplaces, sinais B2B e CNPJ exibido na página.

**Atenção:** o código original de `checar_sites.py` usa `verify=False` nas requisições HTTPS, sem validar certificados TLS. Essa opção reduz a segurança da conexão. Recomenda-se ativar a verificação antes de utilizar com dados sensíveis.

Os CSVs são tratados no formato `;` com codificação `utf-8-sig`.

## Boas práticas

O serviço Docker publicado em `127.0.0.1:8080` não exige autenticação e deve permanecer restrito à máquina local. Revise resultados antes de tratar uma empresa, CNPJ ou site como validado. Evite publicar dados pessoais ou bases de leads no GitHub.
