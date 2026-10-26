#!/usr/bin/env python3
"""Leads do Google Maps (versao BR) - so biblioteca padrao, sem pip install.

Exemplos:
    python scrape_br.py "restaurantes" --cidade "Campinas, SP"
    python scrape_br.py "transportadoras" "operadores logisticos" --cidade "Cuiaba, MT" --cidade "Uberlandia, MG"
    python scrape_br.py --termos-arquivo termos.txt --cidades-arquivo cidades.txt --depth 5

Requer o motor rodando antes:  docker compose up -d

Baseado no google-maps-scraper-kit (MIT, Mahanaicoach); motor: gosom/google-maps-scraper (MIT).
"""
import argparse, csv, io, json, os, re, sys, time
import urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = os.environ.get("SCRAPER_BASE_URL", "http://localhost:8080")
NOMINATIM = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org")
UA = "maps-leads-br/1.0 (uso local)"
LEAD = ["title", "phone", "emails", "website", "site_tipo", "category", "address", "cep", "numero",
        "review_rating", "review_count", "place_id", "latitude", "longitude"]
POLL_SEG = 8

for _s in (sys.stdout, sys.stderr):  # console do Windows (cp1252) nao quebra com acento
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(r, timeout=60) as resp:
        return resp.read()


def geocode(cidade, pais):
    q = {"format": "json", "limit": 1, "q": cidade}
    if pais:
        q["countrycodes"] = pais
    r = urllib.request.Request(f"{NOMINATIM}/search?{urllib.parse.urlencode(q)}", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            hits = json.loads(resp.read())
        time.sleep(1)  # politica do Nominatim: ~1 req/s
        if hits:
            return str(hits[0]["lat"]), str(hits[0]["lon"])
    except Exception as e:
        print(f"  (geocoding falhou: {e})", file=sys.stderr)
    return None


def ler_lista(valores, arquivo):
    itens = list(valores or [])
    if arquivo:
        with open(arquivo, encoding="utf-8-sig") as f:
            itens += [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
    return list(dict.fromkeys(itens))  # sem duplicatas, mantendo a ordem


def rodar_job(termos, cidade, lat, lon, a):
    """Cria 1 job para a cidade, espera terminar e devolve as linhas brutas (ou None se falhar)."""
    keywords = [f"{t} em {cidade}" for t in termos]
    body = {"name": f"br-{cidade}"[:60], "keywords": keywords, "lang": a.lang, "zoom": a.zoom,
            "lat": lat, "lon": lon, "fast_mode": False, "radius": a.raio,
            "depth": a.depth, "email": a.email, "max_time": a.max_time}
    try:
        job_id = json.loads(api("POST", "/api/v1/jobs", body)).get("id")
    except urllib.error.HTTPError as e:
        print(f"  x erro ao criar job: HTTP {e.code} - {e.read().decode('utf-8', 'replace')[:200]}")
        return None
    if not job_id:
        print("  x o motor nao devolveu id do job")
        return None
    limite = time.time() + a.max_time + 120  # acompanha o --max-time, com folga
    status = None
    while time.time() < limite:
        try:
            status = json.loads(api("GET", f"/api/v1/jobs/{job_id}")).get("Status")
        except Exception as e:  # motor ocupado ou timeout: tenta de novo em vez de derrubar a rodada
            print(f"\r  (consulta falhou: {e}) ", end="", flush=True)
            time.sleep(POLL_SEG)
            continue
        print(f"\r  status: {str(status):<10}", end="", flush=True)
        if status in ("ok", "failed"):
            break
        time.sleep(POLL_SEG)
    print()
    if status != "ok":
        print("  x job falhou ou estourou o tempo (possivel bloqueio temporario do Google: espere e reduza o --depth)")
        return None
    try:
        bruto = api("GET", f"/api/v1/jobs/{job_id}/download").decode("utf-8", "replace")
    except Exception as e:
        print(f"  x download falhou: {e}")
        return None
    return list(csv.DictReader(io.StringIO(bruto)))


def chave(r):
    for k in ("place_id", "cid", "link"):
        if r.get(k):
            return (k, r[k])
    return ("nome", (r.get("title", "") + "|" + r.get("address", "")).lower())


SOCIAL_RE = {  # esquema opcional: pega tambem "//instagram.com/x" e "www.instagram.com/x"
    "instagram": re.compile(r"(?:https?:)?(?://)?(?:www\.)?instagram\.com/([A-Za-z0-9_.]+)", re.I),
    "facebook": re.compile(r"(?:https?:)?(?://)?(?:www\.|m\.|web\.|pt-br\.)?facebook\.com/([A-Za-z0-9_.\-]+)", re.I),
    "linkedin": re.compile(r"(?:https?:)?(?://)?(?:[a-z]{2,3}\.)?linkedin\.com/(?:company|in|school)/([A-Za-z0-9_.\-%]+)", re.I),
}
REDE_HOST = re.compile(r"(instagram|facebook|linkedin)\.com", re.I)
AGREGADOR = re.compile(r"linktr\.ee|linkme\.bio|bio\.link|beacons\.ai|taplink|wa\.me|api\.whatsapp|whatsapp\.com|goomer\.app|"
                       r"ifood\.com|anota\.ai|mercadolivre\.com|mercadoshops|shopee\.com|olx\.com|google\.com|youtube\.com|tiktok\.com", re.I)
EMAIL_LIXO = re.compile(r"sentry|wixpress|\.(png|jpe?g|gif|webp|svg)$|^[0-9a-f]{24,}@|example\.|seudominio|dominio\.com", re.I)


def tipo_site(url):
    """proprio = dominio da empresa; rede_social / agregador = presenca digital sem site proprio."""
    if not url:
        return "sem_site"
    host = urllib.parse.urlparse(url if "//" in url else "//" + url).netloc.lower()
    if REDE_HOST.search(host):
        return "rede_social"
    if AGREGADOR.search(host):
        return "agregador"
    return "proprio"


def limpar_emails(v):
    ok = [e.strip() for e in re.split(r"[,;\s]+", v or "") if "@" in e and not EMAIL_LIXO.search(e.strip())]
    return ", ".join(dict.fromkeys(ok))


def endereco(r):
    """CEP e numero para cruzar com a Receita; usa o JSON complete_address e cai no texto de address."""
    cep = num = ""
    try:
        j = json.loads(r.get("complete_address") or "{}")
        cep = re.sub(r"\D", "", j.get("postal_code", ""))
        m = re.search(r",\s*(\d{1,6})\b", j.get("street", ""))
        num = m.group(1) if m else ""
    except Exception:
        pass
    txt = r.get("address") or ""
    if len(cep) != 8:
        m = re.search(r"(\d{5})-?(\d{3})\s*$", txt)
        cep = m.group(1) + m.group(2) if m else ""
    if not num:
        m = re.search(r",\s*(\d{1,6})\s*(?:-|,)", txt)
        num = m.group(1) if m else ""
    return cep, num
IGNORAR = {"", "home", "pages", "people", "help", "about", "policies", "legal", "privacy", "settings",
           "sharer", "tr", "profile.php", "plugins", "dialog", "intent", "login", "share.php", "p", "reel",
           "reels", "explore", "stories", "tv", "watch", "events", "groups", "hashtag", "search", "share", "sharer.php",
           "sharer", "accounts", "direct", "business", "privacy.php", "terms", "l.php", "photo.php", "media", "embed.js"}


def socials_do_site(url):
    out = {"instagram": "", "facebook": "", "linkedin": ""}
    if not url:
        return out
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    html = url  # se o "site" do Maps ja e o perfil da rede, o proprio link responde
    if tipo_site(url) == "proprio":
        html = baixar_home(url)
    for rede, rx in SOCIAL_RE.items():
        for m in rx.finditer(html):
            h = m.group(1).lower().rstrip(".")
            if h in IGNORAR or (rede == "facebook" and (h.isdigit() or len(h) < 3)):
                continue
            achado = m.group(0).rstrip("\"'/.").replace("\\", "")
            out[rede] = "https://" + re.sub(r"^(https?:)?/*", "", achado)
            break
    return out


def baixar_home(url):
    for u in dict.fromkeys((url, url.replace("https://", "http://"))):
        try:
            r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126 Safari/537.36"})
            with urllib.request.urlopen(r, timeout=12) as resp:
                return resp.read(2_000_000).decode("utf-8", "replace")  # rodape com as redes fica no fim do HTML
        except Exception:
            continue
    return ""


def feitas_path(a):
    return a.out + ".cidades_ok.txt"


def carregar_anterior(a):
    """--retomar: recarrega o CSV ja salvo e a lista de cidades concluidas."""
    linhas, feitas = [], set()
    if os.path.exists(a.out):
        with open(a.out, encoding="utf-8-sig", newline="") as f:
            linhas = list(csv.DictReader(f, delimiter=a.sep))
    if os.path.exists(feitas_path(a)):
        with open(feitas_path(a), encoding="utf-8") as f:
            feitas = {l.strip() for l in f if l.strip()}
    return linhas, feitas


def salvar(linhas, campos, a, quieto=False):
    if quieto:
        with open(a.out + ".tmp", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=campos, delimiter=a.sep, extrasaction="ignore")
            w.writeheader()
            w.writerows(linhas)
        os.replace(a.out + ".tmp", a.out)  # troca atomica: queda no meio nao corrompe o CSV
        return
    _salvar(linhas, campos, a)


def _salvar(linhas, campos, a):
    with open(a.out, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: Excel le os acentos
        w = csv.DictWriter(f, fieldnames=campos, delimiter=a.sep, extrasaction="ignore")
        w.writeheader()
        w.writerows(linhas)
    print(f"> {len(linhas)} leads salvos em {a.out}")


EXTRAS = ["site_tipo", "cep", "numero", "cidade_busca", "instagram", "facebook", "linkedin"]


def campos_saida(a, campos_brutos):
    base = campos_brutos if a.full else LEAD
    return list(dict.fromkeys(list(base) + ["site_tipo", "cep", "numero", "cidade_busca"]
                              + (["instagram", "facebook", "linkedin"] if a.socials else [])))


def main():
    ap = argparse.ArgumentParser(description="Leads do Google Maps por termo e cidade (versao BR).")
    ap.add_argument("termos", nargs="*", help='ex.: "restaurantes" "pizzarias"')
    ap.add_argument("--termos-arquivo", help="arquivo com um termo por linha")
    ap.add_argument("--cidade", action="append", help='ex.: "Campinas, SP" (pode repetir)')
    ap.add_argument("--cidades-arquivo", help="arquivo com uma cidade por linha")
    ap.add_argument("--depth", type=int, default=5, help="profundidade da rolagem (padrao 5; mais = mais leads e mais risco)")
    ap.add_argument("--lang", default="pt", help="idioma dos resultados, 2 letras (padrao pt)")
    ap.add_argument("--pais", default="br", help="pais para o geocoding (padrao br; vazio = qualquer)")
    ap.add_argument("--raio", type=int, default=10000, help="raio em metros (padrao 10000)")
    ap.add_argument("--zoom", type=int, default=15)
    ap.add_argument("--max-time", type=int, default=600, help="limite de cada job, em segundos")
    ap.add_argument("--pausa", type=int, default=10, help="segundos de espera entre cidades")
    ap.add_argument("--no-email", dest="email", action="store_false", help="nao buscar e-mails (mais rapido)")
    ap.add_argument("--socials", action="store_true", help="buscar Instagram/Facebook/LinkedIn no site de cada empresa")
    ap.add_argument("--full", action="store_true", help="manter todas as colunas brutas")
    ap.add_argument("--sep", default=";", help="separador do CSV (padrao ';', o do Excel em portugues)")
    ap.add_argument("--out", default="leads.csv")
    ap.add_argument("--retomar", action="store_true", help="continua uma rodada interrompida: pula as cidades ja concluidas")
    a = ap.parse_args()

    termos = ler_lista(a.termos, a.termos_arquivo)
    cidades = ler_lista(a.cidade, a.cidades_arquivo)
    if not termos or not cidades:
        sys.exit("x Informe pelo menos um termo e uma cidade. Veja: python scrape_br.py --help")
    try:
        api("GET", "/api/v1/jobs")
    except Exception as e:
        sys.exit(f"x Motor fora do ar em {BASE}. Rode 'docker compose up -d' e espere ~1 min.\n  ({e})")
    if a.depth >= 15 or len(termos) * len(cidades) >= 10:
        print("! Job grande: sem proxy o Google pode bloquear seu IP por minutos a horas. Seguindo...")

    todas, vistos, campos_brutos, duplicadas = [], set(), [], 0
    feitas = set()
    if a.retomar:
        todas, feitas = carregar_anterior(a)
        vistos = {chave(r) for r in todas}
        campos_brutos = [c for c in (todas[0].keys() if todas else []) if c not in EXTRAS]
        print(f"> Retomando: {len(todas)} leads e {len(feitas)} cidades ja concluidas")
    elif os.path.exists(feitas_path(a)):
        os.remove(feitas_path(a))
    try:
        for i, cidade in enumerate(cidades, 1):
            if cidade in feitas:
                continue
            print(f"[{i}/{len(cidades)}] {cidade}: {', '.join(termos)}")
            coords = geocode(cidade, a.pais)
            if not coords:
                print("  x cidade nao encontrada, pulando")
                continue
            try:
                linhas = rodar_job(termos, cidade, coords[0], coords[1], a)
            except Exception as e:  # uma cidade com erro nao derruba as outras
                print(f"\n  x erro inesperado: {e}")
                linhas = None
            if linhas is None:
                continue
            novas = 0
            for r in linhas:
                k = chave(r)
                if k in vistos:
                    duplicadas += 1
                    continue
                vistos.add(k)
                for c in r:
                    if c not in campos_brutos:
                        campos_brutos.append(c)
                r["cidade_busca"] = cidade
                r["site_tipo"] = tipo_site(r.get("website", ""))
                r["cep"], r["numero"] = endereco(r)
                r["emails"] = limpar_emails(r.get("emails", ""))
                todas.append(r)
                novas += 1
            print(f"  + {novas} novos ({len(linhas)} brutos)")
            salvar(todas, campos_saida(a, campos_brutos), a, quieto=True)  # checkpoint por cidade
            with open(feitas_path(a), "a", encoding="utf-8") as f:
                f.write(cidade + "\n")
            if i < len(cidades):
                time.sleep(a.pausa)
    except KeyboardInterrupt:
        print("\n! Interrompido: salvando o que ja foi coletado.")

    campos = campos_saida(a, campos_brutos)
    if a.socials and todas:
        com_site = [r for r in todas if r.get("website") and not r.get("instagram")]
        print(f"> Buscando redes sociais em {len(com_site)} sites...")
        with ThreadPoolExecutor(max_workers=8) as ex:
            for r, s in zip(com_site, ex.map(lambda r: socials_do_site(r["website"]), com_site)):
                r.update(s)
    salvar(todas, campos, a)
    print(f"  duplicadas removidas: {duplicadas}")
    for r in todas[:5]:
        print(f"  - {r.get('title', '')} | {r.get('phone', '')} | {r.get('emails', '')} | {r.get('website', '')}")


if __name__ == "__main__":
    main()
