#!/usr/bin/env python3
"""contracts-sync.py — 合约登记表(contracts.json)的每轮写回与叠加(v3.5.9,待办 20)。

为什么要有:Evose 里 contracts.json 随发布包进沙箱,是只读的底版;本轮 Lead 用 dex.py pin/block 钉的合约
  只活在沙箱里,沙箱一回收就没了,下一轮又从底版开始——钉过的币重新变成「未钉死,不取价」。
做法(与台账同一思路:每轮写一个新文件,不覆盖):
  开跑  apply  把项目 state/contracts/ 下的全部变化文件,按 run_ts 顺序叠到底版上(底版 _sync.cut_ms 之前的跳过——
               那些已经被本机并进底版了);叠完另存一份开跑快照。
  收尾  diff   比开跑快照与当前登记表,有变化就写 contracts-delta-<run_ts>.json,导出到项目 state/contracts/。
  本机  pull   打发布包前,把项目里的变化文件拉回本机并入 ~/.trend-scout/contracts.json,cut_ms 前移——
               本机仍是唯一的源,下一版底版就带上了 Evose 钉的合约。
合约地址是公开信息,不加密(台账加密是因为有处置记录;这里没有),免解密环境也能用。

用法:
  contracts-sync.py apply <登记表> <变化文件或目录>...   叠加,原地写回登记表
  contracts-sync.py diff <开跑快照> <当前登记表> <run_ts> <输出目录>   有变化才写文件
  contracts-sync.py pull <变化文件或目录>...               本机用:并入 ~/.trend-scout/contracts.json 并前移 cut_ms
"""
import glob, json, os, re, sys

SECS = ('tokens', 'blocked', 'price_map')
NAME = re.compile(r'contracts-delta-(\d{13})\.json$')
LOCAL = os.environ.get('CONTRACTS_JSON') or os.path.expanduser('~/.trend-scout/contracts.json')


def load(p):
    return json.load(open(p, encoding='utf-8'))


def save(p, d):
    json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


def deltas(args):
    fs = []
    for a in args:
        if '*' in a and not os.path.exists(a):
            continue   # 通配符没匹配到(项目里还没有任何变化文件,第一轮必然如此)——等于没有变化文件,不是错
        fs += sorted(glob.glob(os.path.join(a, 'contracts-delta-*.json'))) if os.path.isdir(a) else [a]
    out = []
    for f in fs:
        m = NAME.search(os.path.basename(f))
        if not m:
            sys.exit(f'🚨 文件名不是 contracts-delta-<13位run_ts>.json:{f}')
        d = load(f)
        if str(d.get('run_ts')) != m.group(1):
            sys.exit(f'🚨 {f} 文件名与内容 run_ts 不一致({d.get("run_ts")})——疑似被改名,不叠加')
        out.append((int(m.group(1)), f, d))
    return sorted(out)


def merge(reg, ds, cut):
    n = {'set': 0, 'del': 0, 'skip': 0}; notes = []
    for ts, f, d in ds:
        if ts <= cut:
            n['skip'] += 1; continue
        for op in d.get('ops', []):
            sec, k = op['sec'], op['key']
            if sec not in SECS:
                sys.exit(f'🚨 {f}:未知段 {sec}')
            cur = reg.setdefault(sec, {})
            if op['op'] == 'set':
                if k in cur and cur[k] != op['value']:
                    notes.append(f'{sec}.{k} 被 {ts} 覆盖')
                cur[k] = op['value']; n['set'] += 1
            elif op['op'] == 'del':
                cur.pop(k, None); n['del'] += 1
            else:
                sys.exit(f'🚨 {f}:未知操作 {op["op"]}')
    return n, notes


def cmd_apply(a):
    if len(a) < 1:
        sys.exit(__doc__)
    reg = load(a[0]); cut = int(reg.get('_sync', {}).get('cut_ms', 0))
    ds = deltas(a[1:])
    n, notes = merge(reg, ds, cut)
    save(a[0], reg)
    for x in notes:
        print('  ' + x)
    print(f'CONTRACTS: 变化文件={len(ds)} 叠加={len(ds) - n["skip"]} 跳过(≤底版cut {cut})={n["skip"]} '
          f'写入={n["set"]} 删除={n["del"]} 已钉={len(reg.get("tokens", {}))} 暂不可钉={len(reg.get("blocked", {}))}')


def cmd_diff(a):
    if len(a) != 4:
        sys.exit(__doc__)
    before, after, ts, outd = load(a[0]), load(a[1]), a[2], a[3]
    if not re.fullmatch(r'\d{13}', ts):
        sys.exit('🚨 run_ts 必须是 13 位毫秒数')
    ops = []
    for sec in SECS:
        b, c = before.get(sec, {}), after.get(sec, {})
        for k in sorted(set(b) | set(c)):
            if k not in c:
                ops.append({'op': 'del', 'sec': sec, 'key': k})
            elif b.get(k) != c[k]:
                ops.append({'op': 'set', 'sec': sec, 'key': k, 'value': c[k]})
    if not ops:
        print('CONTRACTS: 本轮登记表无变化,不写文件'); return
    p = os.path.join(outd, f'contracts-delta-{ts}.json')
    if os.path.exists(p):
        sys.exit(f'🚨 {p} 已存在,不覆盖')
    save(p, {'run_ts': int(ts), 'ops': ops})
    print(f'CONTRACTS: 写出 {p} 操作={len(ops)}：' + '、'.join(f'{o["op"]} {o["sec"]}.{o["key"]}' for o in ops))


def cmd_pull(a):
    if not a:
        sys.exit(__doc__)
    reg = load(LOCAL); cut = int(reg.get('_sync', {}).get('cut_ms', 0))
    ds = deltas(a)
    n, notes = merge(reg, ds, cut)
    new = [ts for ts, _, _ in ds if ts > cut]
    if new:
        reg['_sync'] = {'cut_ms': max(new), 'doc': 'contracts-sync.py pull 维护:≤cut_ms 的 Evose 变化文件已并入本文件,开跑叠加时跳过'}
    save(LOCAL, reg)
    for x in notes:
        print('  ' + x)
    print(f'PULL: 变化文件={len(ds)} 新并入={len(new)} 写入={n["set"]} 删除={n["del"]} cut_ms={reg.get("_sync", {}).get("cut_ms", 0)}')


if __name__ == '__main__':
    c = sys.argv[1:2]
    {'apply': cmd_apply, 'diff': cmd_diff, 'pull': cmd_pull}.get(c[0] if c else '', lambda a: sys.exit(__doc__))(sys.argv[2:])
