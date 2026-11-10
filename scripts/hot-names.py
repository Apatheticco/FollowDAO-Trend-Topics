#!/usr/bin/env python3
"""hot-names.py — L2 社媒跨语种「新名字」共现(v3.3.3)。读 news-fetch 的 dump,找同一个**新**名字在短窗内被多源、多语种提及。

**为什么是「新名字」而不是「热词」**:热词(BTC/Robinhood/meme)每天都热,没有信息;热点的特征是一个**昨天不存在的名字**
突然被互不相识的人用不同语言同时喊——09-08 4Stock:越(Solotop_Alpha 13:23)→中(OdailyChina 13:50)→韩(cybertruck666 14:14)→英(PowsGemCalls 14:21),
四语种一小时内,而机审⑦要到 14:35 才亮。
判据:同一新名字 6h 内 ≥3 个不同源 且 ≥2 种语言 → 🔥;≥5 源任意语言 → 🔥;≥2 源 → 👀(只提示)。
新颖性=不在:majors / 停用词 / b0 三天窗口内 created_at 早于 12h 的题(标题+keywords) / actions.tsv 近 7 天已出现的名字。
名字形态:$TICKER;全大写 3-10;字母数字混合(4Stock/BNC4);带点(Four.meme);CamelCase(MarsCoin)。
已知边界:纯中文命名的新币(「牛来」「哈基米」)抓不到——需要中文 NER,v1 不做。
用法: hot-names.py [dump.json ...] [--window 6]   无参=最近 2h 内的 dump;注入 NEWS_DUMP_DIR / HOTNAMES_B0 / HOTNAMES_ACTIONS。
"""
import json, os, re, sys, time, collections

B0=os.environ.get('HOTNAMES_B0') or os.path.expanduser('~/.trend-scout/b0-latest.json')
ACT=os.environ.get('HOTNAMES_ACTIONS') or os.path.expanduser('~/.trend-scout/actions.tsv')
MAJ=os.environ.get('MAJORS_JSON') or os.path.expanduser('~/.trend-scout/majors.json')

STOP=set('''THE AND FOR ARE BUT NOT YOU ALL ANY CAN HAD HER WAS ONE OUR OUT DAY GET HAS HIM HIS HOW MAN NEW NOW OLD SEE TWO WAY WHO BOY DID ITS LET PUT SAY SHE TOO USE
THIS THAT WITH FROM HAVE WILL YOUR MORE WHEN THAN THEM BEEN INTO ONLY OVER SUCH JUST LIKE SOME TIME VERY WHAT ABOUT AFTER AGAIN COULD EVERY FIRST GREAT NEVER OTHER STILL THEIR THERE THESE THOSE WHERE WHICH WHILE WOULD
USDT USDC USD ETF ETFS DEX CEX NFT NFTS DEFI WEB3 KOL TGE FDV MCAP ATH ATL IPO CEO CTO CFO COO APY APR TVL ROI PNL LP LPS DAO DAT RWA AGI LLM API APP PRO MAX TOP ALL
CHAIN TOKEN TOKENS COIN COINS MEME MEMES SWAP SPOT PERP PERPS FUTURES LAUNCH LAUNCHPAD AIRDROP STAKING BRIDGE WALLET VAULT POOL POOLS
BSC ETH SOL BTC BNB BASE ARB SEI SUI TON TRX HYPE OKX BINANCE BYBIT UPBIT BITHUMB COINBASE KRAKEN GATE MEXC KUCOIN HTX
PUMP FOMO HODL WAGMI NGMI GM GN LFG ATH RIP OTC OG
JAN FEB MAR APR MAY JUN JUL AUG SEP SEPT OCT NOV DEC MON TUE WED THU FRI SAT SUN
AM PM UTC EST ET CST KST JST SGT HTTPS HTTP COM NEWS FLASH REPORT DATA LINK TWITTER TELEGRAM YOUTUBE
FED FOMC CPI PPI GDP SEC CFTC IRS ETC USA UK EU CN KR JP HK'''.split())

def _majors():
    try: return {m.upper() for m in json.load(open(MAJ))['majors']}
    except Exception: return set()

NAME_RE=re.compile(r'(?<![A-Za-z0-9])\$?([A-Za-z0-9][A-Za-z0-9.]{1,11})(?![A-Za-z0-9])')
URL_RE=re.compile(r'https?://\S+|\b[\w.-]+\.(?:com|io|xyz|me|fun|finance|app|org|net|co|ai|so|link|news|info)(?:/\S*)?',re.I)
def names_in(text):
    out=set()
    text=URL_RE.sub(' ',text)   # v3.3.3 首跑假阳性:TWITTER.COM/X.COM 被当成名字——URL 碎片先剥掉
    for m in NAME_RE.finditer(text):
        raw=m.group(1); k=raw.upper().strip('.')
        if len(k)<3 or len(k)>12 or k in STOP: continue
        if not re.search(r'[A-Z]',k): continue                       # 纯数字不算
        is_ticker=text[m.start()]=='$'
        allcaps=raw.isupper() and raw.isalpha()
        mixed=bool(re.search(r'\d',raw)) and bool(re.search(r'[A-Za-z]',raw))
        camel=bool(re.match(r'[A-Z][a-z]+[A-Z][A-Za-z]+$',raw))
        dotted='.' in raw.strip('.')
        if is_ticker or allcaps or mixed or camel or dotted: out.add(k)
    return out

def lang_of(text, hint=None):
    if re.search(r'[가-힣]',text): return 'ko'
    if re.search(r'[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]',text,re.I): return 'vi'
    if re.search(r'[一-鿿]',text): return 'zh'
    if re.search(r'[Ѐ-ӿ]',text): return 'ru'
    if re.search(r'[぀-ヿ]',text): return 'ja'
    return (hint or 'en').split('-')[0] if hint else 'en'

def known_names(now_ms):
    known=_majors()|STOP
    try:
        d=json.load(open(B0)); rows=d.get('topics') if isinstance(d,dict) else d
        for t in rows or []:
            try: c=time.mktime(time.strptime(t.get('created_at',''),'%Y-%m-%d %H:%M:%S'))*1000
            except Exception: c=0
            if now_ms-c>12*3600e3: known|=names_in((t.get('title') or '')+' '+(t.get('keywords') or ''))
    except Exception: pass
    try:
        for l in open(ACT,encoding='utf-8',errors='ignore'):
            p=l.rstrip('\n').split('\t')
            if len(p)>4 and p[0].isdigit() and now_ms-int(p[0])<7*86400e3 and now_ms-int(p[0])>12*3600e3:
                known|=names_in(' '.join(p[4:]))
    except Exception: pass
    return known

def scan(dumps, window_h=6):
    now=time.time()*1000; known=known_names(now)
    hits=collections.defaultdict(lambda:{'src':set(),'lang':set(),'first':None,'ex':[]})
    n=0
    for dp in dumps:
        d=json.load(open(dp,encoding='utf-8'))
        for src,items in (d.get('pulls') or {}).items():
            for it in items:
                ts=it.get('ts') or d['ts']
                if now-ts>window_h*3600e3: continue
                n+=1; txt=it.get('text') or ''; lang=lang_of(txt,it.get('lang')); who=it.get('kol') or it.get('name') or src
                for k in names_in(txt):
                    if k in known: continue
                    h=hits[k]; h['src'].add(who); h['lang'].add(lang)
                    h['first']=min(h['first'],ts) if h['first'] else ts
                    _e=(lang,who,re.sub(r'\s+',' ',txt)[:70])
                    if len(h['ex'])<3 and _e not in h['ex']: h['ex'].append(_e)
    rows=[]
    for k,h in hits.items():
        s,l=len(h['src']),len(h['lang'])
        lvl='🔥' if (s>=3 and l>=2) or s>=5 else ('👀' if s>=2 else None)
        if lvl: rows.append((0 if lvl=='🔥' else 1,-s,k,s,sorted(h['lang']),h['first'],h['ex'],lvl))
    rows.sort()
    return n,rows

if __name__=='__main__':
    a=sys.argv[1:]; win=float(a[a.index('--window')+1]) if '--window' in a else 6.0
    dumps=[x for x in a if x.endswith('.json')]
    if not dumps:
        sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
        from news_fetch import recent
        dumps=recent(win)                      # v3.3.5:与 hot-scan 同口径,窗口内全部 dump
    if not dumps:
        print('⚠️ 无 ≤2h 的 news dump(先跑 news-fetch.py)——L2 半盲,不得据此说「社媒无新名字」'); print('HOTNAMES: 候选=0 观察=0 半盲=1'); sys.exit(0)
    n,rows=scan(dumps,win)
    print(f'hot-names {time.strftime("%F %T")} | 条目={n} 窗口={win:g}h | dumps={len(dumps)}')
    fire=sum(1 for r in rows if r[-1]=='🔥'); watch=sum(1 for r in rows if r[-1]=='👀')
    for _,_,k,s,langs,first,ex,lvl in rows[:15]:
        print(f'  {lvl} {k:12s} 源={s} 语种={"/".join(langs)} 首见={time.strftime("%H:%M",time.localtime(first/1000))}')
        for lg,who,t in ex: print(f'       [{lg}] {who[:18]}: {t}')
    if not rows: print('  (无)')
    print(f'HOTNAMES: 候选={fire} 观察={watch} 半盲=0'+('  ← 有候选:切热点模式(gate.sh 大热点)' if fire else ''))
