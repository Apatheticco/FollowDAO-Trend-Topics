#!/usr/bin/env python3
"""leak-guard.py — 导出/推送前查凭证外泄(v3.5.11,2026-09-23)。

为什么要有:Evose 项目文件、对话附件的导出链接免登录公开,删除后链接也不失效;飞书推送进群。
  密钥出现在项目对话里只有项目成员能看(他们本来就能让 Lead 解密台账),落进上述三处才是真外泄。
  此前只有推送一处用 grep -F 查预览文件;Lead 自己导出的报告、journal、变化文件,子 Agent 的产出都没人查。
做法:从环境变量取凭证(LEDGER_KEY 必需,LARK_APP_SECRET 有就一并查),在给定文件/目录里找
  凭证全串及其任意连续 16 字符片段(防截断、换行拆开后仍有一大段原文)。.gz/.tar.gz 解开查;
  .enc 是密文,跳过。命中只报文件路径与凭证名,任何情况下都不打印凭证或文件内容。

用法:leak-guard.py [--fp <LEDGER_KEY 指纹前16位>] [--allow-nokey] <文件或目录>...
  --fp          LEDGER_KEY 的 sha256 前 16 位必须等于它,否则当凭证错了、退出 2(凭证错了查了也白查)
  --allow-nokey 沙箱有 ~/.trend-scout/.BOOTSTRAP-NOKEY(免解密试跑)且没给 LEDGER_KEY 时,记 SKIP、退出 0
退出码:0 无命中;1 命中(不许导出/发送);2 用法错、凭证缺失或不对、文件读不了。
"""
import gzip, hashlib, io, os, sys, tarfile

WIN = 16


def needles(secret):
    s = secret.encode()
    if len(s) <= WIN:
        return {s}
    return {s[i:i + WIN] for i in range(len(s) - WIN + 1)}


def blobs(path):
    """yield (显示名, 字节);.enc 返回 None 表示跳过。"""
    if path.endswith('.enc'):
        yield path, None
        return
    data = open(path, 'rb').read()
    if path.endswith(('.tar.gz', '.tgz')):
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tf:
            for m in tf.getmembers():
                if m.isfile():
                    yield f'{path}!{m.name}', tf.extractfile(m).read()
        return
    if path.endswith('.gz'):
        data = gzip.decompress(data)
    yield path, data


def walk(args):
    for a in args:
        if os.path.isdir(a):
            for root, _, files in os.walk(a):
                for f in sorted(files):
                    yield os.path.join(root, f)
        else:
            yield a


def main(a):
    fp, allow_nokey, paths = None, False, []
    it = iter(a)
    for x in it:
        if x == '--fp':
            fp = next(it, None)
        elif x == '--allow-nokey':
            allow_nokey = True
        else:
            paths.append(x)
    if not paths or (fp is not None and len(fp) != 16):
        print(__doc__, file=sys.stderr); return 2
    key = os.environ.get('LEDGER_KEY', '')
    if not key:
        marker = os.path.expanduser('~/.trend-scout/.BOOTSTRAP-NOKEY')
        if allow_nokey and os.path.exists(marker):
            print('LEAK-GUARD: SKIP 免解密环境,没有密钥可泄'); return 0
        print('🚨 LEAK-GUARD: 没有 LEDGER_KEY 环境变量,查不了——不许导出/发送', file=sys.stderr); return 2
    if fp and hashlib.sha256(key.encode()).hexdigest()[:16] != fp:
        print('🚨 LEAK-GUARD: LEDGER_KEY 指纹不符,查了也白查——不许导出/发送', file=sys.stderr); return 2
    secrets = [('LEDGER_KEY', needles(key))]
    if os.environ.get('LARK_APP_SECRET'):
        secrets.append(('LARK_APP_SECRET', needles(os.environ['LARK_APP_SECRET'])))
    n = skipped = hit = 0
    for p in walk(paths):
        try:
            for name, data in blobs(p):
                if data is None:
                    skipped += 1; continue
                n += 1
                found = [label for label, ns in secrets if any(x in data for x in ns)]
                if found:
                    hit += 1
                    print(f'🚨 疑似含凭证\t{name}\t{"/".join(found)}')
        except (OSError, EOFError, tarfile.TarError, gzip.BadGzipFile) as e:
            print(f'🚨 LEAK-GUARD: 读不了 {p}({type(e).__name__})——不许导出/发送', file=sys.stderr); return 2
    if n == 0 and skipped == 0:
        print('🚨 LEAK-GUARD: 一个文件都没查到(路径写错?)——不许导出/发送', file=sys.stderr); return 2
    print(f'LEAK-GUARD: 查了={n} 跳过密文={skipped} 命中={hit} 凭证={"+".join(l for l, _ in secrets)}')
    return 1 if hit else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
