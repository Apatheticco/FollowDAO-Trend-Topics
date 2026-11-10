#!/usr/bin/env python3
"""风向标排序权重判档(v3.7.30,11-09 用户定并当日 review 修订)。单一定义在 weights.json(WEIGHTS_JSON 可注入)。

档位(全部非负——score≤0 的题会从热榜消失):A 大事件 +600 / B 美股重点 +300 / C 正常 +150 / D 小币 1(=默认)。
- crypto:主流币(市值前 20+USDT/USDC)、头部机构(Tether/币安/Coinbase…)、行业级硬事件(监管执法、被盗≥1亿美元、ETF 审批)→C;其余→D。
- tradfi:
  A=美国宏观(亚股题只认美联储/非农等明确美国口径)|有名有姓的央行利率决议|美股指数|标题主体是超大盘股|百亿美元级 IPO/并购
    |主权政策事件的主切面(价格腿是指数/金价原油美元美债/超大盘股);政策事件的次切面→B
  B=标题主体是核心池 19 只|美股板块/多股题|金价原油美元美债等宏观资产
  C=亚股(标题或建题备注带 .T/.KS/.HK 等)|其余美股个股
- 「主体」=标题里第一个价格动作(收涨/跌/盘前跌…X%)前面那个名字;认不出主体才退回全标题找名字。
- 我建的题以建题时定的档为准(weights-tier.tsv,topic.py 写);人工改档 --tier 也记在这里,最新一行生效。

用法:weight.py <domain> <标题> [keywords] [note]   → 打印 档 权重 依据
"""
import json, os, re, sys

D = os.path.dirname(os.path.abspath(__file__))
PRICE = re.compile(r'(收|盘前|盘后|夜盘|盘中|午盘|尾盘|期货|一度|股价)?(涨|跌)(超|逾|近)?\d')


def cfg():
    return json.load(open(os.environ.get('WEIGHTS_JSON') or os.path.join(D, 'weights.json'), encoding='utf-8'))


def _kws(kws):
    if isinstance(kws, str):
        return [k.strip() for k in re.split(r'[,，]', kws) if k.strip()]
    return [str(k).strip() for k in (kws or []) if str(k).strip()]


def _yi_usd(text):
    """标题里最大的「X亿美元」/「X万亿美元」/「$XB」金额(单位:亿美元);没有返回 0。"""
    best = 0.0
    for m in re.finditer(r'(\d+(?:\.\d+)?)\s*(万亿|亿)\s*美元', text or ''):
        best = max(best, float(m.group(1)) * (10000 if m.group(2) == '万亿' else 1))
    for m in re.finditer(r'\$\s*(\d+(?:\.\d+)?)\s*([BbMm])', text or ''):
        best = max(best, float(m.group(1)) * (10 if m.group(2) in 'Bb' else 0.01))
    return best


def subject(title):
    """标题里第一个价格动作前面的名字(到上一个逗号/顿号/空格为止);没有价格动作返回空串。"""
    m = PRICE.search(title or '')
    if not m:
        return ''
    head = (title or '')[:m.start()]
    seg = re.split(r'[，、；;：:]|,(?!\s)', head)[-1].strip()   # 「Coherent, Inc.」的英文逗号+空格不切
    return seg[-24:]


def _names_hit(names, text):
    """names={ticker:[别名…]};text 里出现 ticker(整词)或任一别名 → 返回 ticker。"""
    for tk, al in names.items():
        if re.search(r'(?<![A-Za-z])' + re.escape(tk) + r'(?![A-Za-z])', text or '') or any(x and x in (text or '') for x in al):
            return tk
    return None


def _megacap_names():
    try:
        return json.load(open(os.environ.get('MEGACAP_JSON') or os.path.join(D, 'megacap.json'), encoding='utf-8')).get('names') or {}
    except Exception:
        return {}


def classify(domain, title, kws='', note=''):
    """返回 (档, 权重, 依据)。"""
    c = cfg()
    T = c['tiers']
    ks = _kws(kws)
    title = title or ''
    hay = title + ' ' + ' '.join(ks)

    def out(tier, why):
        return tier, T[tier]['weight'], why

    if domain == 'crypto':
        majors = set(c['major_coins'])
        if any(k.upper() in majors for k in ks) or any(re.search(r'(?<![A-Za-z])' + m + r'(?![A-Za-z])', title) for m in majors) \
                or any(a.upper() in hay.upper() for a in c.get('major_coin_aliases', [])):
            return out('C', '主流币')
        # 「币安合约成交额X亿美元」是小币纯行情题的价格腿,「币安上线/Alpha」是小币上币事件——都不算头部机构本身的事
        ent_hay = re.sub(r'(币安|Binance|OKX|Coinbase)(合约|现货|永续)?(24小时)?成交额?[\d.]+\s*(亿|万)?美元', '', title)
        ent_hay = re.sub(r'(币安|Binance|OKX|Coinbase)\s*(Alpha|上线|将上线|上架|上币|开放|推出.{0,6}合约)', '', ent_hay)
        m = re.search(c.get('crypto_entities', '^$'), ent_hay + ' ' + ' '.join(k for k in ks if not re.fullmatch(r'(币安|Binance)', k)))
        if m:
            return out('C', f'头部机构({m.group(0)})')
        m = re.search(c['crypto_hard_event'], hay)
        if m:
            if re.search(r'被盗|被黑|遭攻击|黑客', m.group(0)) and _yi_usd(title) < c.get('crypto_hack_min_usd_yi', 1):
                return out('D', f'小币(被盗金额<{c.get("crypto_hack_min_usd_yi", 1)}亿美元)')
            return out('C', f'行业级硬事件({m.group(0)})')
        return out('D', '小币')

    # ---- tradfi ----
    mega, core = _megacap_names(), c.get('core_us') or {}
    subj = subject(title)
    asia = re.search(c['asia_markers'], hay) or (note and re.search(c['asia_note_markers'], note))
    asia_subj = bool(subj and re.search(c['asia_markers'], subj))

    m = re.search(c['macro_cb'], title)
    if m:
        return out('A', f'央行决议({m.group(0)[:12]})')
    m = re.search(c['macro_us_explicit'], title) or (not asia and re.search(c['macro_generic'], title))
    if m:
        return out('A', f'宏观({m.group(0)})')

    m = re.search(c['policy'], title)
    if m:
        # 主切面=价格腿是指数/宏观资产/超大盘股;没有价格动作的(预告、公告形态)本身就是事件主体,也算主切面
        lead = (not PRICE.search(title)) or re.search(c['us_index'], title) or re.search(c['macro_assets'], title) or _names_hit(mega, subj or title)
        if lead and not asia_subj and not (asia and not PRICE.search(title)):
            return out('A', f'主权政策主切面({m.group(0)})')
        if asia:
            return out('C', f'亚股(政策次切面:{m.group(0)})')
        return out('B', f'主权政策次切面({m.group(0)})')

    if not asia and re.search(c['us_index'], title):
        return out('A', f'美股指数({re.search(c["us_index"], title).group(0)})')
    if re.search(c['mega_deal_words'], title) and (any(n.lower() in title.lower() for n in c['mega_deal_names'])
                                                   or _yi_usd(title) >= c.get('mega_deal_min_usd_yi', 100)):
        return out('A', '百亿美元级IPO/并购')

    # 单名题看主体;认不出主体才看全标题
    if subj:
        if asia_subj or (note and re.search(c['asia_note_markers'], note) and not _names_hit(mega, subj) and not _names_hit(core, subj)):
            return out('C', f'亚股({subj})')
        tk = _names_hit(mega, subj)
        if tk:
            return out('A', f'超大盘股({tk})')
        tk = _names_hit(core, subj)
        if tk and not re.search(c['sector_pattern'], title):
            return out('B', f'核心池({tk})')
    else:
        tk = _names_hit(mega, title)
        if tk and not asia:
            return out('A', f'超大盘股({tk})')

    if re.search(c['sector_pattern'], title):
        return out('C', '亚股(板块)') if asia else out('B', '美股板块/多股')
    if _names_hit(core, subj or title) and not asia:
        return out('B', f'核心池({_names_hit(core, subj or title)})')
    m = re.search(c['macro_assets'], title)
    if m:
        return out('B', f'宏观资产({m.group(0)})')
    if asia:
        return out('C', f'亚股({asia.group(0)})')
    return out('C', '美股个股')


def _tier_file(path=None):
    return path or os.environ.get('WEIGHTS_TIER') or os.path.join(D, 'weights-tier.tsv')


def recorded(tid, path=None):
    """weights-tier.tsv 里该 id 最新一行 → (档, 来源, 依据);没有返回 None。来源=auto(建题时自动)/manual(人工 --tier)。"""
    p = _tier_file(path)
    got = None
    if os.path.exists(p):
        for ln in open(p, encoding='utf-8'):
            f = ln.rstrip('\n').split('\t')
            if len(f) >= 5 and f[1] == str(tid) and f[2] in ('A', 'B', 'C', 'D'):
                got = (f[2], f[3], f[4])
    return got


def record(ts, tid, tier, source, why, path=None):
    with open(_tier_file(path), 'a', encoding='utf-8') as f:
        f.write('\t'.join(str(x).replace('\t', ' ').replace('\n', ' ') for x in (ts, tid, tier, source, why)) + '\n')


def tier_weight(tier):
    return cfg()['tiers'][tier]['weight']


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    t, w, why = classify(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else '', sys.argv[4] if len(sys.argv) > 4 else '')
    print(t, w, why)
