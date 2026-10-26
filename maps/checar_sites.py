"""Etapa 4: abre a home de cada site e extrai Instagram, plataforma de e-commerce e carrinho. Sem IA, sem Google.
Uso: python checar_sites.py entrada.csv coluna_do_site saida.csv      (pip install httpx)
"""
import sys, re, asyncio
import pandas as pd, httpx

PLATAFORMAS = {'vtex': r'vtex(assets|commercestable|\.com)|vteximg', 'shopify': r'cdn\.shopify\.com|myshopify',
    'nuvemshop': r'nuvemshop|tiendanube|mitiendanube', 'tray': r'tray(commerce|\.com\.br)|traycdn',
    'loja_integrada': r'lojaintegrada|awsli\.com\.br', 'woocommerce': r'woocommerce|wc-ajax',
    'magento': r'mage/cookies|Magento_|static/version', 'wbuy': r'wbuy', 'bagy': r'bagy\.com', 'yampi': r'yampi',
    'linx': r'linximpulse|core\.dcg\.com\.br', 'wake_fbits': r'fbits', 'opencart': r'route=checkout/cart', 'bling_olist': r'olist|vnda\.com'}
CARRINHO = re.compile(r'adicionar ao carrinho|add[-_ ]to[-_ ]cart|/checkout|/carrinho|minicart|meu carrinho|comprar agora', re.I)
B2B = re.compile(r'area do (cliente|revendedor)|portal do (cliente|representante)|pedido online|seja (um )?(revendedor|distribuidor)', re.I)
INSTA = re.compile(r'instagram\.com/(?!p/|reel/|explore/|accounts/|share)([A-Za-z0-9_.]{2,30})', re.I)
MKT = re.compile(r'(mercadolivre\.com\.br|shopee\.com\.br|magazineluiza\.com\.br|amazon\.com\.br)/[^"\' <]+', re.I)
CNPJ = re.compile(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}')

def analisar(html):
    plat = [k for k, p in PLATAFORMAS.items() if re.search(p, html, re.I)]
    ig = INSTA.search(html); mk = MKT.search(html)
    return {'instagram_site': 'https://instagram.com/' + ig.group(1) if ig else '',
            'plataforma': ','.join(plat), 'tem_carrinho': bool(CARRINHO.search(html)),
            'sinal_b2b': bool(B2B.search(html)), 'marketplace': mk.group(0) if mk else '',
            'cnpj_no_site': ';'.join(sorted(set(CNPJ.findall(html)))[:3]),
            'ja_tem_ecommerce': bool(plat) or bool(CARRINHO.search(html))}

async def baixar(cli, sem, url):
    async with sem:
        for u in (url, url.replace('https://www.', 'https://'), url.replace('https://', 'http://')):
            try:
                r = await cli.get(u, timeout=12)
                if r.status_code < 400 and len(r.text) > 300:
                    return {'site_status': 'ok', 'site_final': str(r.url), **analisar(r.text)}
            except Exception:
                continue
        return {'site_status': 'fora_do_ar'}

async def main(src, col, dst):
    df = pd.read_csv(src, dtype=str, sep=';', encoding='utf-8-sig').fillna('')
    nao_site = re.compile(r'instagram\.com|facebook\.com|linkedin\.com|linktr\.ee|wa\.me|whatsapp|goomer\.app|ifood\.com|mercadolivre|shopee', re.I)
    alvo = df[(df[col] != '') & ~df[col].str.contains(nao_site)]
    sem = asyncio.Semaphore(40)
    async with httpx.AsyncClient(follow_redirects=True, verify=False, headers={'User-Agent': 'Mozilla/5.0'}) as cli:
        res = await asyncio.gather(*[baixar(cli, sem, u if u.startswith('http') else 'https://' + u) for u in alvo[col]])
    df = df.join(pd.DataFrame(res, index=alvo.index))
    df.to_csv(dst, index=False, sep=';', encoding='utf-8-sig')
    print(df['site_status'].value_counts(dropna=False).to_dict())

if __name__ == '__main__':
    asyncio.run(main(*sys.argv[1:4]))
