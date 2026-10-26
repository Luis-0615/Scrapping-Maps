# Maps Leads BR

Lista de leads do Google Maps por termo e cidade, rodando 100% na sua máquina. Sem chave de API e sem custo.

## Pré-requisitos
- Docker Desktop instalado e aberto
- Python 3.8+ (não precisa de `pip install`)

## Passo a passo
1. Abra o terminal nesta pasta.
2. Suba o motor: `docker compose up -d` (a primeira vez baixa a imagem e o navegador; espere 1 a 2 min).
3. Confira: abra http://localhost:8080 no navegador.
4. Rode um teste pequeno:
   ```
   python scrape_br.py "restaurantes" --cidade "Campinas, SP" --depth 2
   ```
5. Abra o `leads.csv` no Excel.
6. Ao terminar: `docker compose down`.

## Exemplos
| Caso | Comando |
|---|---|
| Vários termos, uma cidade | `python scrape_br.py "hoteis" "moteis" "academias" --cidade "Goiania, GO"` |
| Várias cidades | `python scrape_br.py "transportadoras" --cidade "Cuiaba, MT" --cidade "Uberlandia, MG"` |
| Listas em arquivo | `python scrape_br.py --termos-arquivo termos.txt --cidades-arquivo cidades.txt` |
| Sem e-mail (rápido) | `python scrape_br.py "padarias" --cidade "Santos, SP" --no-email` |
| Com redes sociais | `python scrape_br.py "clinicas" --cidade "Joinville, SC" --socials` |
| Rodada grande, retomável | `python scrape_br.py --termos-arquivo termos.txt --cidades-arquivo cidades.txt --no-email --depth 5 --retomar` |
| Todas as colunas | `python scrape_br.py "bares" --cidade "Niteroi, RJ" --full --out bares.csv` |

## Opções principais
| Opção | Padrão | O que faz |
|---|---|---|
| `--depth` | 5 | Quanto rola a lista do Maps; mais alto traz mais leads e mais risco de bloqueio |
| `--lang` | pt | Idioma dos resultados |
| `--raio` | 10000 | Raio da busca em metros a partir do centro da cidade |
| `--max-time` | 600 | Limite de cada job, em segundos |
| `--pausa` | 10 | Espera entre cidades, em segundos |
| `--sep` | ; | Separador do CSV (o do Excel em português) |
| `--retomar` | desligado | Continua uma rodada interrompida, pulando as cidades já concluídas |

## O que muda em relação ao kit original
- Resultados em português (`lang=pt`)
- Um job por cidade, em sequência, com a coluna `cidade_busca`
- Duplicatas removidas por `place_id`
- CSV em `utf-8-sig` com `;`, que abre direto no Excel com acentos
- Espera do job acompanha o `--max-time`
- Se uma cidade falhar, as outras continuam; Ctrl+C salva o que já foi coletado
- O CSV é gravado a cada cidade; `--retomar` continua de onde parou (controle em `<saida>.cidades_ok.txt`)
- Colunas novas: `site_tipo` (proprio, rede_social, agregador, sem_site), `cep`, `numero`, `place_id`
- `--raio` não é filtro rígido no modo normal do motor: o Maps pode trazer empresas de fora do raio
- Em cidade grande, use bairros ou zonas no arquivo de cidades (ex.: `Mooca, São Paulo, SP`)

## Cuidados
- Comece com `--depth 2` a `5` e poucas cidades; volume alto sem proxy gera bloqueio temporário de IP.
- Scraping do Maps contraria os termos de uso do Google.
- Telefones e e-mails são dados pessoais (LGPD).

## Créditos
Baseado no google-maps-scraper-kit (MIT, Mahanaicoach). Motor: gosom/google-maps-scraper (MIT, Georgios Komninos).
