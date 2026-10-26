"""Etapa 3: cruza a saída do scraper do Google Maps com a Receita enriquecida.
Uso: python cruzar_maps.py leads.csv receita_enriquecida.csv leads_com_cnpj.csv
Chaves, em ordem de confiança: telefone > CEP+número > nome parecido no mesmo município.
"""
import sys, re, json, unicodedata
import pandas as pd
try:
    from rapidfuzz import fuzz
    sim = lambda a, b: fuzz.token_set_ratio(a, b)
except ImportError:
    from difflib import SequenceMatcher
    sim = lambda a, b: 100 * SequenceMatcher(None, a, b).ratio()

STOP = {'ltda','me','epp','eireli','sa','comercio','industria','de','e','do','da','dos','das','para','com'}
def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii','ignore').decode().lower()
    return ' '.join(t for t in re.sub(r'[^a-z0-9 ]', ' ', s).split() if t not in STOP)
def fone(s):
    d = re.sub(r'\D', '', str(s or ''))
    if d.startswith('55') and len(d) > 11: d = d[2:]
    d = d.lstrip('0')
    return d if len(d) in (10, 11) else ''
def end_maps(j):
    try: a = json.loads(j)
    except Exception: return '', '', ''
    cep = re.sub(r'\D', '', a.get('postal_code', ''))
    m = re.search(r',\s*(\d{1,6})\b', a.get('street', ''))
    return cep, (m.group(1) if m else ''), norm(a.get('city', ''))

def main(maps_csv, receita_csv, dst, corte_nome=88):
    m = pd.read_csv(maps_csv, dtype=str, sep=';', encoding='utf-8-sig').fillna('')
    r = pd.read_csv(receita_csv, dtype=str, sep=';', encoding='utf-8-sig').fillna('')
    r['mun'] = r['Município'].map(norm)
    r['n1'] = r['Razão Social'].map(norm); r['n2'] = r['Nome Fantasia'].map(norm)
    # telefone repetido em vários CNPJs costuma ser do contador: não serve de chave
    por_fone = r[(r.fone_norm != '') & (r.fone_qtd.astype(int) == 1)].set_index('fone_norm')
    por_end = r[r.num_end != ''].drop_duplicates(['cep8', 'num_end'], keep=False).set_index(['cep8', 'num_end'])
    por_mun = {k: g for k, g in r.groupby('mun')}
    out = []
    for _, x in m.iterrows():
        cep, num, cid = end_maps(x.get('complete_address', ''))
        if not cep: cep = re.sub(r'\D', '', str(x.get('cep', '') or ''))
        if not num: num = str(x.get('numero', '') or '')
        if not cid: cid = norm(str(x.get('cidade_busca', '')).split(',')[0])
        ad = str(x.get('address', '') or '')
        if len(cep) != 8:
            mm = re.search(r'(\d{5})-?(\d{3})\s*$', ad); cep = mm.group(1) + mm.group(2) if mm else ''
        if not num:
            mm = re.search(r',\s*(\d{1,6})\s*(?:-|,)', ad); num = mm.group(1) if mm else ''
        f = fone(x.get('phone', '')); nome = norm(x['title'])
        hit, chave, score = None, '', 0
        if f and f in por_fone.index: hit, chave, score = por_fone.loc[f], 'telefone', 100
        elif (cep, num) in por_end.index: hit, chave, score = por_end.loc[(cep, num)], 'cep+numero', 95
        elif cid in por_mun:
            g = por_mun[cid]
            s = g.apply(lambda y: max(sim(nome, y['n1']), sim(nome, y['n2']) if y['n2'] else 0), axis=1)
            if len(s) and s.max() >= corte_nome and (s >= corte_nome).sum() == 1:
                hit, chave, score = g.loc[s.idxmax()], 'nome+municipio', round(s.max())
        d = x.to_dict()
        d.update({'match_chave': chave, 'match_score': score})
        for c in ['CNPJ','Razão Social','Nome Fantasia','Porte','Capital Social','Simples','Filiais Ativas','CNAE Principal','faixa_porte','flag_pesado','E-mail','Sócio 1']:
            d['rf_' + c] = hit[c] if hit is not None else ''
        out.append(d)
    o = pd.DataFrame(out)
    drop = [c for c in ['user_reviews','user_reviews_extended','images','thumbnail','popular_times','about','open_hours'] if c in o]
    o.drop(columns=drop).to_csv(dst, index=False, sep=';', encoding='utf-8-sig')
    print(f"{len(o)} leads do Maps | com CNPJ: {(o.match_chave != '').sum()} |", o.match_chave.replace('', 'sem match').value_counts().to_dict())
    return o

if __name__ == '__main__':
    main(*sys.argv[1:4])
