"""Testes locais basicos do coletor Maps, sem acessar sites ou a API."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def importar(nome):
    spec = importlib.util.spec_from_file_location(nome, ROOT / (nome + ".py"))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


maps = importar("scrape_br")
sites = importar("checar_sites")
cruzar = importar("cruzar_maps")


class ScraperTests(unittest.TestCase):
    def test_tipo_site(self):
        self.assertEqual(maps.tipo_site("https://instagram.com/exemplo"), "rede_social")
        self.assertEqual(maps.tipo_site("https://empresa.com.br"), "proprio")
        self.assertEqual(maps.tipo_site(""), "sem_site")

    def test_endereco(self):
        cep, numero = maps.endereco({
            "complete_address": '{"postal_code":"12345-678","street":"Rua A, 100"}'
        })
        self.assertEqual((cep, numero), ("12345678", "100"))

    def test_arquivo_de_termos_remove_duplicatas_e_comentarios(self):
        with tempfile.TemporaryDirectory() as pasta:
            path = Path(pasta) / "termos.txt"
            path.write_text("# comentario\nautopecas\nautopecas\ncomercio\n", encoding="utf-8")
            self.assertEqual(maps.ler_lista([], str(path)), ["autopecas", "comercio"])


class SiteTests(unittest.TestCase):
    def test_analisar_pagina(self):
        texto = 'instagram.com/empresa <button>adicionar ao carrinho</button> CNPJ 11.222.333/0001-44'
        result = sites.analisar(texto)
        self.assertEqual(result["instagram_site"], "https://instagram.com/empresa")
        self.assertTrue(result["tem_carrinho"])
        self.assertTrue(result["ja_tem_ecommerce"])
        self.assertEqual(result["cnpj_no_site"], "11.222.333/0001-44")


class CruzamentoTests(unittest.TestCase):
    def test_normalizar_razao_social(self):
        self.assertEqual(cruzar.norm("Comércio São Pedro LTDA"), "sao pedro")

    def test_normalizar_telefone(self):
        self.assertEqual(cruzar.fone("+55 (11) 91234-5678"), "11912345678")

    def test_endereco_do_maps(self):
        self.assertEqual(
            cruzar.end_maps('{"postal_code":"12345-678","street":"Rua A, 100","city":"São Paulo"}'),
            ("12345678", "100", "sao paulo"),
        )


if __name__ == "__main__":
    unittest.main()
