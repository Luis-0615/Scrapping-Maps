import argparse
import asyncio
import csv
import pandas as pd
import json
import os
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse


from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

BASE = "https://www.linkedin.com"

COLUNAS = [
    "tipo",
    "nome_exibido",
    "linkedin_url",
    "funcionarios",
    "empresa",
    "cargo_pesquisado",
    "consulta",
    "status",
    "texto_coletado"
]

# Reconhecimento das faixas de funcionarios
NUM = r"\d[\d.,]*"
INTERVALO = (
    rf"({NUM}[ \t]*"
    rf"(?:[-\u2010-\u2015]|\ba\b|\bto\b)"
    rf"[ \t]*{NUM}|{NUM}[ \t]*\+)"
)

ROTULO = (
    r"(?:Company[ \t]+size|"
    r"Tamanho[ \t]+da[ \t]+empresa|"
    r"Porte[ \t]+da[ \t]+empresa|"
    r"Tamanho[ \t]+da[ \t]+organiza(?:ção|cao))"
)

PADRAO_FAIXA = re.compile(
    rf"{ROTULO}[ \t]*:?[ \t]*"
    rf"(?:\r?\n[ \t]*){{0,2}}{INTERVALO}",
    re.IGNORECASE
)

PADRAO_FALLBACK = re.compile(
    rf"(?m)^[ \t]*{INTERVALO}[ \t]*"
    rf"(?:employees|funcionários|funcionarios)\b",
    re.IGNORECASE
)


class ConsultaLimitada(RuntimeError):
    pass


def simplificar(valor):
    texto = unicodedata.normalize(
        "NFKD", str(valor)
    ).casefold()

    return "".join(
        c for c in texto
        if not unicodedata.combining(c)
    ).strip()


def chrome_instalado():
    candidatos = [os.environ.get("CHROME_PATH", "")]

    candidatos.extend(
        str(
            Path(os.environ[base])
            / "Google/Chrome/Application/chrome.exe"
        )
        for base in (
            "ProgramFiles",
            "ProgramFiles(x86)",
            "LOCALAPPDATA"
        )
        if os.environ.get(base)
    )

    return next(
        (
            p for p in candidatos
            if p and Path(p).is_file()
        ),
        None
    )


def extrair_funcionarios(dados):
    """
    Extrai a faixa declarada no perfil da empresa.
    Nao confunde perfis associados com empregados reais.
    """

    texto = str(
        (dados.get("sections") or {}).get("about") or ""
    )

    if not texto:
        return ""

    achado = (
        PADRAO_FAIXA.search(texto)
        or PADRAO_FALLBACK.search(texto)
    )

    if not achado:
        return ""

    valor = achado.group(1)
    numeros = re.findall(NUM, valor)

    def inteiro(s):
        return str(
            int(s.replace(".", "").replace(",", ""))
        )

    if len(numeros) == 2:
        return (
            f"{inteiro(numeros[0])} "
            f"a {inteiro(numeros[1])}"
        )

    if len(numeros) == 1 and "+" in valor:
        return inteiro(numeros[0]) + "+"

    return ""


def referencias(dados, tipo):
    """Itera referencias MCP; URNs nem sempre possuem um campo URL."""
    grupos = dados.get("references") or {}
    if not isinstance(grupos, dict):
        return

    for grupo in grupos.values():
        if isinstance(grupo, dict):
            grupo = [grupo]
        if not isinstance(grupo, (list, tuple)):
            continue

        for ref in grupo:
            if not isinstance(ref, dict) or ref.get("kind") != tipo:
                continue
            if tipo == "company_urn" and ref.get("value") is not None:
                yield ref
            elif ref.get("url"):
                yield ref


def url_completa(caminho):
    """Aceita apenas links de perfis ou empresas do LinkedIn."""
    endereco = urljoin(BASE + "/", str(caminho or "").strip())
    parsed = urlparse(endereco)
    host = (parsed.hostname or "").lower()
    partes = parsed.path.strip("/").split("/")

    if (
        parsed.scheme not in ("http", "https")
        or not (host == "linkedin.com" or host.endswith(".linkedin.com"))
        or len(partes) < 2
        or partes[0] not in ("in", "company")
        or not partes[1]
    ):
        raise ValueError(f"URL do LinkedIn nao suportada: {caminho}")

    return f"{BASE}/{partes[0]}/{partes[1]}/"


def limite_detectado(valor):
    texto = simplificar(valor)
    return any(indicador in texto for indicador in (
        "rate_limit", "rate limit", "rate-limit", "ratelimit",
        "too many requests", "429", "limite de requisicoes"
    ))


def extrair_resposta(resp):
    blocos = getattr(resp, "content", None) or []
    if getattr(resp, "is_error", False):
        mensagem = " ".join(
            getattr(bloco, "text", "") for bloco in blocos
        ) or "O MCP retornou um erro"
        if limite_detectado(mensagem):
            raise ConsultaLimitada(mensagem)
        raise RuntimeError(mensagem)

    dados = getattr(resp, "structured_content", None)
    if not isinstance(dados, dict):
        dados = None
        for bloco in blocos:
            if getattr(bloco, "type", "") != "text":
                continue
            try:
                candidato = json.loads(bloco.text)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(candidato, dict):
                dados = candidato
                break

    if not isinstance(dados, dict):
        raise RuntimeError("Resposta do MCP nao reconhecida")

    if isinstance(dados.get("result"), dict) and "sections" not in dados:
        dados = dados["result"]

    erros = dados.get("section_errors") or {}
    if (
        limite_detectado(erros)
        or limite_detectado(dados.get("error", ""))
        or limite_detectado(dados.get("message", ""))
    ):
        raise ConsultaLimitada("O LinkedIn limitou a consulta")

    return dados

class Servidor:
    def __init__(self, sessao, pausa):
        self.sessao = sessao
        self.pausa = pausa
        self.contagem = 0

    async def chamar(self, ferramenta, argumentos):
        if self.contagem:
            await asyncio.sleep(self.pausa)

        self.contagem += 1

        print(
            f"Consultando {ferramenta}: {argumentos}",
            flush=True
        )

        try:
            resposta = await self.sessao.call_tool(
                ferramenta,
                arguments=argumentos
            )
        except Exception as exc:
            if limite_detectado(exc):
                raise ConsultaLimitada("O LinkedIn limitou a consulta") from exc
            raise

        return extrair_resposta(resposta)


def linha(
    tipo,
    nome,
    link,
    consulta,
    *,
    funcionarios="",
    empresa="",
    cargo="",
    texto="",
    status="candidato_nao_validado"
):
    return {
        "tipo": tipo,
        "nome_exibido": nome,
        "linkedin_url": link,
        "funcionarios": funcionarios,
        "empresa": empresa,
        "cargo_pesquisado": cargo,
        "consulta": consulta,
        "status": status,
        "texto_coletado": texto
    }


# =========================================
# MODO 1: BUSCAR EMPRESAS
# =========================================

async def buscar_empresas(srv, args):
    consultas = args.termos or [
        f"{args.segmento} {args.regiao}".strip(),
        args.segmento
    ]

    consultas = list(
        dict.fromkeys(
            q for q in consultas if q.strip()
        )
    )

    linhas = []
    brutos = []
    vistos = set()

    for consulta in consultas:
        try:
            busca = await srv.chamar(
                "search_companies",
                {"keywords": consulta}
            )
        except ConsultaLimitada:
            print(
                "Limite do LinkedIn detectado. "
                "Interrompendo busca."
            )
            break

        brutos.append({
            "ferramenta": "search_companies",
            "consulta": consulta,
            "resposta": busca
        })

        for ref in referencias(busca, "company"):
            if len(linhas) >= args.limite:
                break

            try:
                url = url_completa(ref["url"])
            except ValueError:
                continue

            if url in vistos:
                continue

            vistos.add(url)

            faixa = ""
            texto = ""
            status = "sem_faixa"

            # Consulta o perfil para obter funcionarios
            try:
                perfil = await srv.chamar(
                    "get_company_profile",
                    {"company_name": url}
                )

                brutos.append({
                    "ferramenta": "get_company_profile",
                    "consulta": url,
                    "resposta": perfil
                })

                faixa = extrair_funcionarios(perfil)

                texto = str(
                    (perfil.get("sections") or {})
                    .get("about") or ""
                )

                status = (
                    "faixa_encontrada"
                    if faixa else "sem_faixa"
                )

            except ConsultaLimitada:
                print(
                    "Limite detectado. "
                    "Salvando resultados parciais."
                )

                linhas.append(linha(
                    "empresa",
                    ref.get("text", ""),
                    url,
                    consulta,
                    status="limite_atingido"
                ))

                return linhas, brutos

            except Exception as exc:
                brutos.append({
                    "ferramenta": "get_company_profile",
                    "consulta": url,
                    "erro": str(exc)
                })

                status = "erro_consulta"

            linhas.append(linha(
                "empresa",
                ref.get("text", ""),
                url,
                consulta,
                funcionarios=faixa,
                texto=texto,
                status=status
            ))

        if len(linhas) >= args.limite:
            break

    return linhas, brutos


# =========================================
# IDENTIFICAR EMPRESA
# =========================================

async def resolver_empresa(srv, empresa, brutos):
    parsed = urlparse(empresa)
    host = (parsed.hostname or "").lower()

    if parsed.scheme in ("http", "https"):
        dominio_valido = (
            host == "linkedin.com"
            or host.endswith(".linkedin.com")
        )

        if dominio_valido and "/company/" in parsed.path:
            return url_completa(empresa)

        raise ValueError(
            "Informe a URL do LinkedIn ou "
            "o nome da empresa"
        )

    busca = await srv.chamar(
        "search_companies",
        {"keywords": empresa}
    )

    brutos.append({
        "ferramenta": "search_companies",
        "consulta": empresa,
        "resposta": busca
    })

    candidatas = list(
        referencias(busca, "company")
    )

    exatas = [
        r for r in candidatas
        if simplificar(r.get("text", ""))
        == simplificar(empresa)
    ]

    if len(exatas) == 1:
        return url_completa(exatas[0]["url"])

    sugestoes = ", ".join(
        url_completa(r["url"])
        for r in candidatas[:5]
    )

    raise ValueError(
        "Empresa nao identificada de forma unica. "
        "Informe a URL /company/. "
        f"Sugestoes: {sugestoes}"
    )


# =========================================
# MODO 2: BUSCAR PROFISSIONAIS
# =========================================

async def buscar_pessoas(srv, args):
    brutos = []

    empresa_url = await resolver_empresa(
        srv,
        args.empresa,
        brutos
    )

    perfil = await srv.chamar(
        "get_company_profile",
        {"company_name": empresa_url}
    )

    brutos.append({
        "ferramenta": "get_company_profile",
        "consulta": empresa_url,
        "resposta": perfil
    })

    # Faixa de funcionarios da empresa
    faixa = extrair_funcionarios(perfil)

    # Identificador numerico exigido no filtro
    urn = next(
        (
            str(ref.get("value"))
            for ref in referencias(
                perfil, "company_urn"
            )
            if re.fullmatch(
                r"\d+",
                str(ref.get("value", ""))
            )
        ),
        None
    )

    if urn:
        ferramenta = "search_people"

        parametros = {
            "keywords": args.cargo,
            "current_company": urn
        }

        if args.regiao:
            parametros["location"] = args.regiao

    else:
        ferramenta = "get_company_employees"

        parametros = {
            "company_name": empresa_url,
            "keywords": args.cargo
        }

        print(
            "Empresa sem URN. Pesquisando na "
            "aba de funcionarios sem filtro regional."
        )

    resultado = await srv.chamar(
        ferramenta,
        parametros
    )

    brutos.append({
        "ferramenta": ferramenta,
        "consulta": args.cargo,
        "resposta": resultado
    })

    linhas = []
    vistos = set()

    for ref in referencias(
        resultado, "person"
    ):
        try:
            url = url_completa(ref["url"])
        except ValueError:
            continue

        if url in vistos:
            continue

        vistos.add(url)

        linhas.append(linha(
            "pessoa",
            ref.get("text", ""),
            url,
            args.cargo,
            empresa=empresa_url,
            cargo=args.cargo,
            funcionarios=faixa
        ))

        if len(linhas) >= args.limite:
            break

    return linhas, brutos


# =========================================
# LEITURA DOS LINKS RECEBIDOS
# =========================================

def carregar_links(args):
    valores = list(args.urls)

    if args.arquivo:
        arquivo = Path(args.arquivo)

        if arquivo.suffix.lower() == ".csv":
            with arquivo.open(
                encoding="utf-8-sig",
                newline=""
            ) as f:

                leitor = csv.DictReader(f)

                colunas = {
                    "url",
                    "linkedin_url",
                    "linkedin",
                    "link",
                    "perfil"
                }

                coluna = next(
                    (
                        c for c in (
                            leitor.fieldnames or []
                        )
                        if simplificar(c) in colunas
                    ),
                    None
                )

                if not coluna:
                    raise ValueError(
                        "CSV precisa de uma coluna "
                        "url ou linkedin_url"
                    )

                valores += [
                    r.get(coluna, "")
                    for r in leitor
                ]

        else:
            valores += arquivo.read_text(
                encoding="utf-8-sig"
            ).splitlines()

    selecionados = []
    for valor in valores:
        try:
            selecionados.append(url_completa(valor))
        except ValueError:
            print(f"Ignorando URL nao suportada: {valor}")

    return list(dict.fromkeys(selecionados))


# =========================================
# MODO 3: CONSULTAR LINKS
# =========================================

async def consultar_links(srv, args):
    linhas = []
    brutos = []

    links = carregar_links(args)

    for url in links[:args.limite]:
        pessoa = "/in/" in url

        ferramenta = (
            "get_person_profile"
            if pessoa
            else "get_company_profile"
        )

        parametros = (
            {"linkedin_username": url}
            if pessoa
            else {"company_name": url}
        )

        if pessoa and args.contato:
            parametros["sections"] = "contact_info"

        try:
            dados = await srv.chamar(
                ferramenta,
                parametros
            )

        except ConsultaLimitada:
            print(
                "Limite detectado. "
                "Interrompendo consultas."
            )
            break

        except Exception as exc:
            brutos.append({
                "ferramenta": ferramenta,
                "consulta": url,
                "erro": str(exc)
            })

            linhas.append(linha(
                "pessoa" if pessoa else "empresa",
                "",
                url,
                "consulta_por_url",
                status="erro_consulta"
            ))
            continue

        brutos.append({
            "ferramenta": ferramenta,
            "consulta": url,
            "resposta": dados
        })

        secoes = dados.get("sections") or {}

        texto = "\n".join(
            f"{nome}: {conteudo}"
            for nome, conteudo in secoes.items()
        )

        # Funcionarios somente para empresas
        faixa = (
            ""
            if pessoa
            else extrair_funcionarios(dados)
        )

        linhas.append(linha(
            "pessoa" if pessoa else "empresa",
            "",
            url,
            "consulta_por_url",
            funcionarios=faixa,
            texto=texto,
            status=(
                "lido"
                if texto
                else "sem_conteudo"
            )
        ))

    return linhas, brutos


# =========================================
# EXPORTACAO
# =========================================

def gravar(modo, linhas, brutos):
    pasta = Path("resultados_linkedin")
    pasta.mkdir(exist_ok=True)

    nome = (
        f"{modo}_"
        f"{datetime.now():%Y%m%d_%H%M%S}"
    )

    df = pd.DataFrame(linhas, columns=COLUNAS)
    df.to_csv(
        pasta / f"{nome}.csv",
        index=False,
        encoding="utf-8-sig"
    )
    df.to_excel(
        pasta / f"{nome}.xlsx",
        index=False,
        sheet_name="Resultados",
        engine="openpyxl"
    )
    (
        pasta / f"{nome}.json"
    ).write_text(
        json.dumps(
            brutos,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print(
        f"{len(linhas)} registros encontrados. "
        f"Arquivos em: {pasta.resolve()}"
    )


# =========================================
# EXECUTAR MCP SEM CODEX
# =========================================

async def executar(args):
    chrome = chrome_instalado()

    if not chrome:
        raise RuntimeError(
            "Chrome nao encontrado. "
            "Configure CHROME_PATH apontando "
            "para chrome.exe."
        )

    parametros = StdioServerParameters(
        command="uvx",
        args=[
            "mcp-server-linkedin@latest"
        ],
        env={
            **os.environ,
            "CHROME_PATH": chrome,
            "UV_HTTP_TIMEOUT": "300"
        }
    )

    async with stdio_client(
        parametros
    ) as (ler, escrever):

        async with ClientSession(
            ler, escrever
        ) as sessao:

            await sessao.initialize()

            srv = Servidor(
                sessao,
                args.pausa
            )

            if args.modo == "empresas":
                linhas, brutos = (
                    await buscar_empresas(srv, args)
                )

            elif args.modo == "pessoas":
                linhas, brutos = (
                    await buscar_pessoas(srv, args)
                )

            else:
                linhas, brutos = (
                    await consultar_links(srv, args)
                )

            gravar(
                args.modo,
                linhas,
                brutos
            )


# =========================================
# ARGUMENTOS
# =========================================

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Consultas via LinkedIn MCP, sem Codex"
        )
    )

    parser.add_argument(
        "--pausa",
        type=float,
        default=5,
        help="Segundos entre consultas"
    )

    subs = parser.add_subparsers(
        dest="modo",
        required=True
    )

    empresas = subs.add_parser("empresas")

    empresas.add_argument(
        "--segmento",
        required=True
    )

    empresas.add_argument(
        "--regiao",
        default=""
    )

    empresas.add_argument(
        "--termos",
        nargs="+"
    )

    empresas.add_argument(
        "--limite",
        type=int,
        default=10
    )

    pessoas = subs.add_parser("pessoas")

    pessoas.add_argument(
        "--empresa",
        required=True
    )

    pessoas.add_argument(
        "--cargo",
        required=True
    )

    pessoas.add_argument(
        "--regiao",
        default=""
    )

    pessoas.add_argument(
        "--limite",
        type=int,
        default=10
    )

    links = subs.add_parser("links")

    links.add_argument(
        "urls",
        nargs="*"
    )

    links.add_argument("--arquivo")

    links.add_argument(
        "--contato",
        action="store_true"
    )

    links.add_argument(
        "--limite",
        type=int,
        default=10
    )

    args = parser.parse_args()

    if not 1 <= args.limite <= 50:
        parser.error(
            "O limite do piloto deve estar "
            "entre 1 e 50"
        )

    if args.pausa < 0:
        parser.error(
            "A pausa nao pode ser negativa"
        )

    if (
        args.modo == "links"
        and not args.urls
        and not args.arquivo
    ):
        parser.error(
            "Informe URLs ou --arquivo"
        )

    try:
        asyncio.run(
            executar(args)
        )

    except (
        RuntimeError,
        ValueError,
        OSError
    ) as exc:

        print(
            f"Erro: {exc}",
            file=sys.stderr
        )

        sys.exit(1)


if __name__ == "__main__":
    main()
