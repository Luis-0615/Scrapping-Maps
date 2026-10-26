"""Testes locais: nao fazem login nem consultam o LinkedIn."""
import asyncio
import csv
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

try:
    import mcp  # noqa: F401
except ImportError:
    mcp_mod = types.ModuleType("mcp")
    mcp_mod.ClientSession = object
    mcp_mod.StdioServerParameters = object
    client_mod = types.ModuleType("mcp.client")
    stdio_mod = types.ModuleType("mcp.client.stdio")
    stdio_mod.stdio_client = lambda *_args, **_kwargs: None
    sys.modules.update({
        "mcp": mcp_mod,
        "mcp.client": client_mod,
        "mcp.client.stdio": stdio_mod,
    })

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scrapping_linkedin as s  # noqa: E402


def resposta(dados=None, *, erro=False, texto=""):
    return SimpleNamespace(
        is_error=erro,
        structured_content=dados,
        content=[SimpleNamespace(type="text", text=texto)] if texto else [],
    )


def test_simplificar_acentos():
    assert s.simplificar("  São PAULO ") == "sao paulo"


def test_funcionarios_pt():
    assert s.extrair_funcionarios({"sections": {"about": "Tamanho da empresa: 51 a 200"}}) == "51 a 200"


def test_funcionarios_en():
    assert s.extrair_funcionarios({"sections": {"about": "Company size: 1,001-5,000"}}) == "1001 a 5000"


def test_funcionarios_fallback():
    assert s.extrair_funcionarios({"sections": {"about": "201-500 employees"}}) == "201 a 500"


def test_funcionarios_sem_faixa():
    assert s.extrair_funcionarios({"sections": {"about": "About the company"}}) == ""


def test_referencias_urn_sem_url():
    data = {"references": {"companies": [{"kind": "company_urn", "value": "1234"}]}}
    assert list(s.referencias(data, "company_urn"))[0]["value"] == "1234"


def test_referencias_grupos_invalidos():
    assert list(s.referencias({"references": {"outros": None}}, "person")) == []


def test_url_normalizada():
    assert s.url_completa("https://br.linkedin.com/company/microsoft/about/?trk=abc") == "https://www.linkedin.com/company/microsoft/"


def test_url_relativa():
    assert s.url_completa("/in/pessoa-teste/?trk=a") == "https://www.linkedin.com/in/pessoa-teste/"


def test_url_externa_recusada():
    with pytest.raises(ValueError):
        s.url_completa("https://www.linkedin.com.evil.test/company/acme/")


def test_extrair_resposta_normal():
    assert s.extrair_resposta(resposta({"result": {"sections": {"about": "ok"}}}))["sections"]["about"] == "ok"


def test_extrair_resposta_json_texto():
    assert s.extrair_resposta(resposta(None, texto=json.dumps({"sections": {"about": "x"}})))["sections"]["about"] == "x"


def test_limite_em_section_errors():
    with pytest.raises(s.ConsultaLimitada):
        s.extrair_resposta(resposta({"section_errors": {"about": "rate_limit"}}))


def test_limite_em_erro_mcp():
    with pytest.raises(s.ConsultaLimitada):
        s.extrair_resposta(resposta(erro=True, texto="HTTP 429 too many requests"))


def test_carregar_links_csv(tmp_path):
    arq = tmp_path / "urls.csv"
    arq.write_text(
        "linkedin_url\nhttps://www.linkedin.com/company/microsoft/?trk=x\n"
        "https://example.org/x\nhttps://www.linkedin.com/company/microsoft/\n",
        encoding="utf-8",
    )
    out = s.carregar_links(SimpleNamespace(urls=[], arquivo=str(arq)))
    assert out == ["https://www.linkedin.com/company/microsoft/"]


def test_buscar_pessoas_filtra_urn_e_regiao():
    class FakeServer:
        def __init__(self):
            self.calls = []

        async def chamar(self, nome, args):
            self.calls.append((nome, args))
            if nome == "get_company_profile":
                return {
                    "sections": {"about": "Company size: 11-50"},
                    "references": {"ids": [{"kind": "company_urn", "value": "987"}]},
                }
            return {"references": {"pessoas": [
                {"kind": "person", "url": "/in/teste/", "text": "Pessoa Exemplo"},
            ]}}

    fake = FakeServer()
    args = SimpleNamespace(
        empresa="https://www.linkedin.com/company/empresa/",
        cargo="diretor", regiao="São Paulo", limite=10,
    )
    linhas, _ = asyncio.run(s.buscar_pessoas(fake, args))
    assert fake.calls[-1] == (
        "search_people",
        {"keywords": "diretor", "current_company": "987", "location": "São Paulo"},
    )
    assert linhas[0]["funcionarios"] == "11 a 50"
    assert linhas[0]["status"] == "candidato_nao_validado"


def test_gravar_tres_formatos(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s.gravar(
        "empresas",
        [s.linha("empresa", "Teste", "https://www.linkedin.com/company/teste/", "teste")],
        [],
    )
    pasta = tmp_path / "resultados_linkedin"
    assert len(list(pasta.glob("*.csv"))) == 1
    assert len(list(pasta.glob("*.xlsx"))) == 1
    assert len(list(pasta.glob("*.json"))) == 1
    with next(pasta.glob("*.csv")).open(encoding="utf-8-sig", newline="") as f:
        assert next(csv.DictReader(f))["nome_exibido"] == "Teste"
