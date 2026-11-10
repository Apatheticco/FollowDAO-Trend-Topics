#!/usr/bin/env python3
"""ledger-sync.py — 本机台账 → Evose 项目的持续同步（v3.5.12，2026-09-23）。

为什么要有:并行期本机每天照跑 09:40/14:40/23:00(晚间轮 v3.7.21 由 22:00 改),Evose 跑 16:30;Evose 判「8h 内有没有相关题」得看到本机刚写的台账。
  09-10 的一次性迁移要 Lead 在同一个沙箱里现生成密钥、现解包,40 分钟寿命内做完,每天做一遍太重。
做法:一对长期密钥。私钥用台账密钥加密后存项目 `ledger/inbox-key/`,公钥交本机;
  本机随时把整份台账打包、用公钥加密放进项目 `ledger/inbox/`(本机全程不需要台账密钥);
  Evose 开跑时用台账密钥解开私钥 → 打开最新同步包作台账底版 → 再追加 Evose 自己写的各轮分片。
  同步包以本机为准,取代旧的 `-migration` 迁移分片;Evose 各轮分片不在本机台账里,一律追加(包里 includes_shards 列出的除外,
  留给以后反向同步用)。

子命令:
  keygen <输出目录>              沙箱里,要 LEDGER_KEY:生成 RSA-4096,私钥用台账密钥加密成 inbox-priv.pem.enc,公钥 inbox-pub.pem
  pack <公钥> <输出目录> [--final] 本机:把 ~/.trend-scout 台账＋reports/ 的复审与周报＋最近一份每晚复盘 retro/<日期>.md 打包,
                                写 sync-<cut>.tar.gz.enc ＋ sync-<cut>.key.rsa;--final＝本机已停写看板(托管后每晚发的包都带),
                                cut 取打包时刻(本机不再出 last-refresh),Evose 开跑见到它不设同步包 12 小时时效
  open <目录>                    沙箱里,要 LEDGER_KEY:目录里放 inbox-priv.pem.enc 与同步包;取 cut 最大的一对,解开铺进 ~/.trend-scout
  append <目录>                  沙箱里:把目录里已解密的各轮分片(旁边有同名 .enc 的才算)按 run_ts 追加到台账
  mark                          沙箱里:记下当前各台账的字节数与内容哈希、reports/ 文件名(append 结束时自动做一次;没有同步包、手拼台账后手动跑)
  delta <run_ts> <输出目录>        沙箱里:按 mark 切出各台账本轮增量写成 <前缀>-<run_ts>.csv,新出现的复审/周报原样拷出;写完把 mark 前移
                                (v3.5.13:第 27 轮 Lead 手挑增量,漏了 review-verify.log——正式轮丢了它,下一轮 lark-push send 会拒发)
通用参数:--fp <LEDGER_KEY 指纹前16位>(keygen/open 必给);环境变量 OPENSSL 指定 openssl(本机 LibreSSL 时自动改用 Homebrew 的)。
凭证只从环境变量读,任何输出都不打印凭证、私钥、传输密钥或台账内容。
"""
import glob, gzip, hashlib, io, json, os, re, shutil, subprocess, sys, tarfile, tempfile, time

HOME = os.path.expanduser('~/.trend-scout')
LEDGERS = {  # 项目分片前缀 → 沙箱文件名
    'actions': 'actions.tsv', 'snapshots': 'snapshots.tsv', 'checklists': 'checklists.log.tsv',
    'event-watch': 'event-watch.tsv', 'circuit': 'circuit-log.tsv', 'drift': 'drift.tsv',
    'pushes': 'lark-push.log.tsv', 'review-verify': 'review-verify.log.tsv', 'rejected': 'actions-rejected.tsv',
    'last-refresh': 'last-refresh.txt',
}
REPORT_RE = re.compile(r'^(review-.+\.(md|txt)|weekly-.+\.md)$')
SHARD_RE = re.compile(r'^(%s)-(\d{13})\.csv$' % '|'.join(map(re.escape, LEDGERS)))
PENDING_RE = re.compile(r'^pending-(\d{13})-(.+)\.json$')
SYNC_RE = re.compile(r'^sync-(\d{13})\.tar\.gz\.enc$')


def die(msg, code=2):
    print('🚨 LEDGER-SYNC: ' + msg, file=sys.stderr); sys.exit(code)


def ossl():
    o = os.environ.get('OPENSSL', 'openssl')
    try:
        v = subprocess.run([o, 'version'], capture_output=True, text=True).stdout
    except OSError:
        die(f'找不到 openssl({o})')
    if 'LibreSSL' in v:
        for alt in ('/opt/homebrew/bin/openssl', '/usr/local/opt/openssl@3/bin/openssl'):
            if os.path.exists(alt):
                return alt
        die('本机 openssl 是 LibreSSL,不支持 OAEP-SHA256;装 OpenSSL 3 或设 OPENSSL')
    return o


def run(args, what):
    r = subprocess.run(args, capture_output=True)
    if r.returncode != 0:
        die(f'{what} 失败(openssl 退出码 {r.returncode})')


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def need_key(fp):
    k = os.environ.get('LEDGER_KEY', '')
    if not k:
        die('没有 LEDGER_KEY 环境变量')
    if not fp or len(fp) != 16:
        die('必须给 --fp <指纹前16位>')
    if hashlib.sha256(k.encode()).hexdigest()[:16] != fp:
        die('LEDGER_KEY 指纹不符')


OAEP = ['-pkeyopt', 'rsa_padding_mode:oaep', '-pkeyopt', 'rsa_oaep_md:sha256', '-pkeyopt', 'rsa_mgf1_md:sha256']


def cmd_keygen(a, fp):
    if len(a) != 1:
        die(__doc__)
    need_key(fp); o = ossl(); out = a[0]; os.makedirs(out, exist_ok=True)
    pub, penc = os.path.join(out, 'inbox-pub.pem'), os.path.join(out, 'inbox-priv.pem.enc')
    for p in (pub, penc):
        if os.path.exists(p):
            die(f'{p} 已存在,不覆盖')
    os.umask(0o077)
    with tempfile.TemporaryDirectory() as t:
        priv, back = os.path.join(t, 'priv.pem'), os.path.join(t, 'back.pem')
        run([o, 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:4096', '-out', priv], '生成私钥')
        run([o, 'pkey', '-in', priv, '-pubout', '-out', pub], '导出公钥')
        run([o, 'enc', '-aes-256-cbc', '-pbkdf2', '-salt', '-in', priv, '-out', penc, '-pass', 'env:LEDGER_KEY'], '加密私钥')
        run([o, 'enc', '-d', '-aes-256-cbc', '-pbkdf2', '-in', penc, '-out', back, '-pass', 'env:LEDGER_KEY'], '回解私钥')
        same = open(priv, 'rb').read() == open(back, 'rb').read()
    if not same:
        os.remove(penc); os.remove(pub); die('私钥加密自检不一致,已删除输出')
    print(f'KEYGEN: 公钥={pub} sha256={sha(pub)} 私钥密文={penc} {os.path.getsize(penc)}字节 自检=一致(明文私钥已删)')


def cut_of(home):
    vals = re.findall(r'\b(\d{13})\b', open(os.path.join(home, 'last-refresh.txt'), encoding='utf-8').read())
    if not vals:
        die('last-refresh.txt 里没有 13 位时间戳,定不了 cut')
    return max(vals)


def cmd_pack(a, fp, final=False):
    if len(a) != 2:
        die(__doc__)
    o = ossl(); pub, out = a; home = os.environ.get('LEDGER_SYNC_HOME', HOME)
    os.makedirs(out, exist_ok=True)
    with tempfile.TemporaryDirectory() as t:
        stage = os.path.join(t, 'stage'); os.makedirs(os.path.join(stage, 'reports'))
        for f in LEDGERS.values():  # 先拷快照再算哈希:本机下一轮可能正在追加
            src = os.path.join(home, f)
            if not os.path.exists(src):
                die(f'本机缺台账 {f}')
            shutil.copy2(src, os.path.join(stage, f))
        reps = sorted(f for f in os.listdir(os.path.join(home, 'reports')) if REPORT_RE.match(f))
        for f in reps:
            shutil.copy2(os.path.join(home, 'reports', f), os.path.join(stage, 'reports', f))
        # v3.7.11(10-22 循环第 3 环):最近一份每晚复盘随包走,Evose 沙箱里 retro.py brief 读它,把「今天注意」打进扫描员/审核员材料
        rd = os.path.join(home, 'retro')
        rts = sorted(f for f in os.listdir(rd) if re.fullmatch(r'\d{4}-\d{2}-\d{2}\.md', f)) if os.path.isdir(rd) else []
        if rts:
            os.makedirs(os.path.join(stage, 'retro'))
            shutil.copy2(os.path.join(rd, rts[-1]), os.path.join(stage, 'retro', rts[-1]))
        cut = str(int(time.time() * 1000)) if final else cut_of(stage)
        base = os.path.join(out, f'sync-{cut}')
        for p in (base + '.tar.gz.enc', base + '.key.rsa'):
            if os.path.exists(p):
                die(f'{p} 已存在,不覆盖(本机从上次同步后还没跑新一轮?)')
        files = {}
        for root, _, fs in os.walk(stage):
            for f in fs:
                p = os.path.join(root, f); rel = os.path.relpath(p, stage)
                files[rel] = {'sha256': sha(p), 'bytes': os.path.getsize(p)}
        # v3.7.11（10-22 回流）：本机用 evose-backfill.py 补记过的 Evose 分片记在 evose-included.txt，列进 includes_shards，
        #   Evose 开跑 append 时跳过——否则这些行在同步包里有一份、Evose 自己的分片再追加一份（10-20 起手抄补记的轮次在 Evose 台账里重复）
        ip = os.path.join(home, 'evose-included.txt')
        inc = sorted({l.strip() for l in open(ip, encoding='utf-8') if l.strip()}) if os.path.exists(ip) else []
        man = {'cut_ms': int(cut), 'created': time.strftime('%Y-%m-%d %H:%M:%S'), 'includes_shards': inc, 'files': files, 'final': bool(final)}
        json.dump(man, open(os.path.join(stage, 'SYNC-MANIFEST.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        pkg = os.path.join(t, 'pkg.tar.gz')
        with tarfile.open(pkg, 'w:gz') as tf:
            for rel in ['SYNC-MANIFEST.json'] + sorted(files):
                tf.add(os.path.join(stage, rel), arcname=rel)  # 保留 mtime:lark-push 按 mtime 认当前复审
        tk = os.path.join(t, 'tk.hex')
        old = os.umask(0o077)
        open(tk, 'w').write(os.urandom(32).hex()); os.umask(old)
        run([o, 'enc', '-aes-256-cbc', '-pbkdf2', '-salt', '-in', pkg, '-out', base + '.tar.gz.enc', '-pass', 'file:' + tk], '加密同步包')
        run([o, 'pkeyutl', '-encrypt', '-pubin', '-inkey', pub] + OAEP + ['-in', tk, '-out', base + '.key.rsa'], '用公钥锁传输密钥')
    nrev = sum(1 for f in files if f.startswith('reports/review-')); nwk = sum(1 for f in files if f.startswith('reports/weekly-'))
    nrt = sum(1 for f in files if f.startswith('retro/'))
    print(f'PACK: cut={cut} 台账={len(LEDGERS)} 复审={nrev} 周报={nwk} 文件={len(files)} 包内已含 Evose 分片={len(inc)} 复盘={nrt}'
          f'{" 终版(本机已停写)" if final else ""} 公钥sha256={sha(pub)[:16]}')
    for p in (base + '.tar.gz.enc', base + '.key.rsa'):
        print(f'  {os.path.basename(p)}\t{os.path.getsize(p)}\t{sha(p)}')


def cmd_open(a, fp, overwrite):
    if len(a) != 1:
        die(__doc__)
    need_key(fp); o = ossl(); d = a[0]; home = os.environ.get('LEDGER_SYNC_HOME', HOME)
    penc = os.path.join(d, 'inbox-priv.pem.enc')
    if not os.path.exists(penc):
        die(f'{d} 里没有 inbox-priv.pem.enc')
    cuts = sorted(SYNC_RE.match(f).group(1) for f in os.listdir(d) if SYNC_RE.match(f))
    if not cuts:
        die(f'{d} 里没有 sync-<cut>.tar.gz.enc')
    cut = cuts[-1]; enc, krsa = os.path.join(d, f'sync-{cut}.tar.gz.enc'), os.path.join(d, f'sync-{cut}.key.rsa')
    if not os.path.exists(krsa):
        die(f'缺 sync-{cut}.key.rsa(同步包要成对)')
    os.umask(0o077)
    with tempfile.TemporaryDirectory() as t:
        priv, tk, pkg = os.path.join(t, 'priv.pem'), os.path.join(t, 'tk.hex'), os.path.join(t, 'pkg.tar.gz')
        run([o, 'enc', '-d', '-aes-256-cbc', '-pbkdf2', '-in', penc, '-out', priv, '-pass', 'env:LEDGER_KEY'], '解开私钥')
        run([o, 'pkeyutl', '-decrypt', '-inkey', priv] + OAEP + ['-in', krsa, '-out', tk], '解开传输密钥')
        run([o, 'enc', '-d', '-aes-256-cbc', '-pbkdf2', '-in', enc, '-out', pkg, '-pass', 'file:' + tk], '解开同步包')
        try:
            tf = tarfile.open(pkg, 'r:gz')
            mem = {m.name: m for m in tf.getmembers() if m.isfile()}
            man = json.load(tf.extractfile(mem['SYNC-MANIFEST.json']))
        except Exception as e:
            die(f'同步包读不出清单({type(e).__name__})')
        if str(man.get('cut_ms')) != cut:
            die(f'包内 cut {man.get("cut_ms")} 与文件名 {cut} 不一致——疑似被改名')
        bad = [n for n, v in man['files'].items() if n not in mem or hashlib.sha256(tf.extractfile(mem[n]).read()).hexdigest() != v['sha256']]
        if bad or set(mem) - set(man['files']) - {'SYNC-MANIFEST.json'}:
            die(f'包内文件与清单不符 {len(bad)} 个')
        for n in man['files']:
            if '..' in n.split('/') or n.startswith('/'):
                die(f'包内路径非法 {n}')
            dst = os.path.join(home, n)
            if os.path.exists(dst) and os.path.getsize(dst) > 0 and not overwrite:
                die(f'{dst} 已存在且非空:同步包只能铺在空环境上(免解密试跑环境加 --overwrite)')
        os.makedirs(os.path.join(home, 'reports'), exist_ok=True)
        if any(n.startswith('retro/') for n in man['files']):
            os.makedirs(os.path.join(home, 'retro'), exist_ok=True)
        for n in man['files']:
            if hasattr(tarfile, 'data_filter'):
                tf.extract(mem[n], home, filter='data')  # data 过滤器同样保留 mtime
            else:
                tf.extract(mem[n], home)  # 保留 mtime
        tf.close()
    json.dump({'cut_ms': int(cut), 'includes_shards': man.get('includes_shards', []), 'final': bool(man.get('final'))},
              open(os.path.join(home, '.sync-base.json'), 'w', encoding='utf-8'))
    nrev = sum(1 for f in man['files'] if f.startswith('reports/review-')); nwk = sum(1 for f in man['files'] if f.startswith('reports/weekly-'))
    print(f'SYNC: cut={cut} 文件={len(man["files"])} 台账={sum(1 for f in man["files"] if f in LEDGERS.values())} 复审={nrev} 周报={nwk} '
          f'清单核对=一致 包内已含分片={len(man.get("includes_shards", []))} 终版={"是" if man.get("final") else "否"} 私钥与传输密钥=已删')


def cmd_append(a):
    if len(a) != 1:
        die(__doc__)
    d = a[0]; home = os.environ.get('LEDGER_SYNC_HOME', HOME)
    bp = os.path.join(home, '.sync-base.json')
    if not os.path.exists(bp):
        die('没有 .sync-base.json:先跑 open')
    base = json.load(open(bp, encoding='utf-8')); inc = set(base.get('includes_shards', []))
    cand = sorted(f for f in os.listdir(d) if os.path.exists(os.path.join(d, f + '.enc')))  # 只认解密出来的(旁边有 .enc)
    shards, reps, pend, n_mig, n_inc, n_same = [], [], [], 0, 0, 0
    for f in cand:
        if '-migration' in f:
            n_mig += 1; continue
        if f + '.enc' in inc:
            n_inc += 1; continue
        m = SHARD_RE.match(f)
        if m:
            shards.append((m.group(2), m.group(1), f)); continue
        m = PENDING_RE.match(f)
        if m:
            pend.append((f, f'{m.group(1)}-{m.group(2)}.json')); continue
        if REPORT_RE.match(f):
            reps.append(f)
    rows = 0
    for ts, name, f in sorted(shards):
        data = open(os.path.join(d, f), 'rb').read()
        if data and not data.endswith(b'\n'):
            data += b'\n'
        dst = os.path.join(home, LEDGERS[name])
        prev = open(dst, 'rb').read() if os.path.exists(dst) else b''
        with open(dst, 'ab') as w:
            if prev and not prev.endswith(b'\n'):
                w.write(b'\n')
            w.write(data)
        rows += data.count(b'\n')
    for f in reps:
        src, dst = os.path.join(d, f), os.path.join(home, 'reports', f)
        if os.path.exists(dst):
            n_same += 1; continue  # 同名以同步包为准(旧迁移分片里的复审,本机也有)
        shutil.copy2(src, dst)
        m = re.search(r'(\d{13})', f)  # 解密出来的 mtime 是解密那一刻,会被 lark-push 当成最新复审;按文件名里的 run_ts 摆回去
        if m:
            t = int(m.group(1)) / 1000
            os.utime(dst, (t, t))
    os.makedirs(os.path.join(home, 'lark-pending'), exist_ok=True)
    for f, to in pend:
        shutil.copy2(os.path.join(d, f), os.path.join(home, 'lark-pending', to))
    lr = os.path.join(home, 'last-refresh.txt')  # 末行为准:Evose 旧轮追加在后,末行可能比本机新值还早
    lines = [l for l in open(lr, encoding='utf-8').read().splitlines() if l.strip()]
    mx = max((l for l in lines if re.fullmatch(r'\d{13}', l.strip())), default=None)
    fixed = 0
    if mx and lines[-1].strip() != mx:
        open(lr, 'a', encoding='utf-8').write(mx + '\n'); fixed = 1
    print(f'APPEND: 分片={len(shards)} 追加行={rows} 复审/周报放入={len(reps) - n_same} 同名以同步包为准={n_same} 待补发={len(pend)} '
          f'跳过迁移分片={n_mig} 跳过包内已含={n_inc} last-refresh末行补正={fixed}')
    write_mark(home)  # 本轮增量从这里算起(第 13 步 delta 用)


MARK = '.sync-mark.json'


def snapshot(home):
    led = {}
    for f in LEDGERS.values():
        p = os.path.join(home, f)
        b = open(p, 'rb').read() if os.path.exists(p) else b''
        led[f] = {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}
    rd = os.path.join(home, 'reports')
    reps = sorted(f for f in os.listdir(rd) if REPORT_RE.match(f)) if os.path.isdir(rd) else []
    return {'ledgers': led, 'reports': reps}


def write_mark(home):
    m = snapshot(home)
    json.dump(m, open(os.path.join(home, MARK), 'w', encoding='utf-8'), ensure_ascii=False)
    return m


def cmd_mark(a):
    home = os.environ.get('LEDGER_SYNC_HOME', HOME)
    m = write_mark(home)
    print(f'MARK: 台账={len(m["ledgers"])} 总字节={sum(v["bytes"] for v in m["ledgers"].values())} 复审/周报={len(m["reports"])}')


def cmd_delta(a):
    if len(a) != 2 or not re.fullmatch(r'\d{13}', a[0]):
        die(__doc__)
    ts, out = a; home = os.environ.get('LEDGER_SYNC_HOME', HOME)
    mp = os.path.join(home, MARK)
    if not os.path.exists(mp):
        die('没有 .sync-mark.json:开跑拼完台账后要先 mark(ledger-sync.py append 会自动做)')
    mark = json.load(open(mp, encoding='utf-8'))
    os.makedirs(out, exist_ok=True)
    plan = []
    for pre, f in LEDGERS.items():
        p = os.path.join(home, f)
        b = open(p, 'rb').read() if os.path.exists(p) else b''
        m = mark['ledgers'].get(f, {'bytes': 0, 'sha256': hashlib.sha256(b'').hexdigest()})
        if len(b) < m['bytes'] or hashlib.sha256(b[:m['bytes']]).hexdigest() != m['sha256']:
            die(f'{f} 不是只追加(开跑后的内容被改过或截短),不许切增量——停下报告')
        if len(b) > m['bytes']:
            dst = os.path.join(out, f'{pre}-{ts}.csv')
            if os.path.exists(dst):
                die(f'{dst} 已存在:同一台账本轮已写过一片,不覆盖')
            plan.append((pre, dst, b[m['bytes']:]))
    rd = os.path.join(home, 'reports')
    newrep = [f for f in (sorted(os.listdir(rd)) if os.path.isdir(rd) else []) if REPORT_RE.match(f) and f not in mark['reports']]
    for f in newrep:
        if os.path.exists(os.path.join(out, f)):
            die(f'{os.path.join(out, f)} 已存在,不覆盖')
    for pre, dst, data in plan:
        open(dst, 'wb').write(data)
        nl = data.count(b'\n')
        print(f'  {os.path.basename(dst)}\t{nl}行\t{len(data)}字节')
    for f in newrep:
        shutil.copy2(os.path.join(rd, f), os.path.join(out, f))
        print(f'  {f}\t(新复审/周报)')
    write_mark(home)
    unchanged = [f for pre, f in LEDGERS.items() if pre not in {p for p, _, _ in plan}]
    print(f'DELTA: run_ts={ts} 写出分片={len(plan)} 新复审/周报={len(newrep)} 未变={len(unchanged)} mark=已前移')


def main(argv):
    fp, overwrite, final, rest = None, False, False, []
    it = iter(argv)
    for x in it:
        if x == '--fp':
            fp = next(it, None)
        elif x == '--overwrite':
            overwrite = True
        elif x == '--final':
            final = True
        else:
            rest.append(x)
    if not rest:
        die(__doc__)
    c, a = rest[0], rest[1:]
    if c == 'keygen':
        cmd_keygen(a, fp)
    elif c == 'pack':
        cmd_pack(a, fp, final)
    elif c == 'open':
        cmd_open(a, fp, overwrite)
    elif c == 'append':
        cmd_append(a)
    elif c == 'mark':
        cmd_mark(a)
    elif c == 'delta':
        cmd_delta(a)
    else:
        die(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
