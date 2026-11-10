#!/usr/bin/env python3
"""repo-sync.py — 脚本/用例/配置 与规则仓库镜像的对账与同步(v3.7.32,2026-11-10)。

为什么要有:~/.trend-scout 此前没有任何版本管理,改坏了只能翻 .bak(11-10 清点 184 个);规则文字在仓库里、
  执行它的脚本却不在,同一版规则对应哪版脚本查不到。
为什么是「镜像」而不是把脚本搬进仓库再软链回来:实测软链后 python 把 sys.path[0] 解析到仓库目录,
  而各脚本用「自己所在目录」找台账——被别的脚本 import 时会去仓库目录找台账,找不到只当空表,不报错
  (撞名表、下游回读这类检查会静默放行);回归用例全靠注入临时路径,测不到默认路径。另外仓库一旦切分支/
  stash,正在跑的轮次脚本会当场变。所以:本机目录照旧是运行目录,仓库 scripts/ 留一份镜像。

进仓库:顶层 *.py *.sh *.awk(含软链)、tests/ 全部、CONFIGS 里人手维护的配置。
不进:流水台账、缓存、.bak、NOT_MIRRORED 里写明原因的文件。

用法:
  repo-sync.py status              对账。首行 MIRROR: …;全一致退出 0,有差异退出 1
  repo-sync.py snapshot            本机 → 仓库镜像(先查敏感内容,命中即停、什么都不拷;不执行 git)
  repo-sync.py restore <路径>...    仓库镜像 → 本机,只动点名的文件(回滚某个脚本用)
  repo-sync.py restore --missing   只补本机没有的文件(新机器初始化用),已有的一律不覆盖
退出码:0 一致/完成;1 有差异;2 用法错、敏感内容命中、目录不存在。
注入(回归):TS_DIR(本机目录) TS_MIRROR(仓库镜像目录)。
"""
import getpass, hashlib, os, re, shutil, sys

TS = os.environ.get('TS_DIR') or os.path.expanduser('~/.trend-scout')
MIRROR = os.environ.get('TS_MIRROR') or os.path.expanduser('~/Desktop/FollowDAO-Trend-Topics/scripts')

CONFIGS = ['channels.json', 'contracts.json', 'majors.json', 'megacap.json', 'weights.json', 'scatter-watch.json']
NOT_MIRRORED = {
    'run-auto.sh': '休眠的本机定时启动器,里面写死本机用户目录',
    'lark.json': '飞书群号与人员 id——仓库是公开的',
}
MIRROR_ONLY = {'README.md'}          # 只在仓库里有、不算「仓库多出」
CODE_RE = re.compile(r'\.(py|sh|awk)$')

# 仓库是公开的:镜像前逐文件查这些形态。只报文件名与类别,不打印内容。
GUARDS = [
    ('飞书群/人员/应用 id', re.compile(rb'\b(?:oc|ou)_[0-9a-f]{20,}|\bcli_[0-9a-z]{14,}')),
    ('本机用户目录', re.compile(rb'/Users/[A-Za-z0-9_]+')),
    ('邮箱地址', re.compile(rb'[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}')),
    ('疑似密钥', re.compile(rb'sk-ant-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._-]{20,}|x-api-key["\']?\s*[:=]\s*["\'][^"\']{12,}', re.I)),
]


def skip(name):
    return '.bak' in name or name in ('.DS_Store',) or name.endswith('.pyc')


def manifest(root, mirror_side=False):
    """返回 {相对路径: 绝对路径}。两边用同一套规则,镜像侧额外不看 MIRROR_ONLY。"""
    out = {}
    if not os.path.isdir(root):
        return out
    for f in sorted(os.listdir(root)):
        p = os.path.join(root, f)
        if skip(f) or f in NOT_MIRRORED or (mirror_side and f in MIRROR_ONLY):
            continue
        if os.path.isdir(p) and not os.path.islink(p):
            continue
        if CODE_RE.search(f) or f in CONFIGS or (mirror_side and (os.path.isfile(p) or os.path.islink(p))):
            out[f] = p
    td = os.path.join(root, 'tests')
    for base, dirs, files in os.walk(td):
        dirs[:] = sorted(d for d in dirs if d != '__pycache__')
        for f in sorted(files):
            if not skip(f):
                p = os.path.join(base, f)
                out[os.path.relpath(p, root)] = p
    return out


def sig(p):
    if os.path.islink(p):
        return 'link:' + os.readlink(p)
    with open(p, 'rb') as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def diff():
    a, b = manifest(TS), manifest(MIRROR, mirror_side=True)
    changed = sorted(r for r in a if r in b and sig(a[r]) != sig(b[r]))
    new = sorted(r for r in a if r not in b)
    extra = sorted(r for r in b if r not in a)
    return a, b, changed, new, extra


def guard(a):
    user = getpass.getuser().encode()
    hits = []
    for rel, p in a.items():
        if os.path.islink(p):
            continue
        data = open(p, 'rb').read()
        kinds = [label for label, rx in GUARDS if rx.search(data)]
        if len(user) >= 4 and user in data:
            kinds.append('本机用户名')
        if kinds:
            hits.append((rel, kinds))
    return hits


def put(src, dst):
    os.makedirs(os.path.dirname(dst) or '.', exist_ok=True)
    if os.path.lexists(dst):
        os.remove(dst)
    if os.path.islink(src):
        os.symlink(os.readlink(src), dst)
    else:
        shutil.copy2(src, dst)


def cmd_status():
    if not os.path.isdir(MIRROR):
        print(f'MIRROR: 仓库镜像目录不存在({MIRROR})——先跑 snapshot'); return 1
    a, b, changed, new, extra = diff()
    same = len(a) - len(changed) - len(new)
    print(f'MIRROR: 文件={len(a)} 一致={same} 改动未入库={len(changed)} 新文件未入库={len(new)} 仓库多出={len(extra)}')
    for r in changed: print(f'  改动\t{r}')
    for r in new: print(f'  新增\t{r}')
    for r in extra: print(f'  多出\t{r}\t(本机已无,snapshot 会从镜像删掉)')
    if changed or new or extra:
        print('  → 改完脚本、回归全过后跑 repo-sync.py snapshot,再随规则一起提交')
        return 1
    return 0


def cmd_snapshot():
    if not os.path.isdir(TS):
        print(f'🚨 本机目录不存在: {TS}', file=sys.stderr); return 2
    a, b, changed, new, extra = diff()
    hits = guard(a)
    if hits:
        for rel, kinds in hits:
            print(f'🚨 不宜进公开仓库\t{rel}\t{"/".join(kinds)}')
        print('SNAPSHOT: 已停,一个文件都没拷——改掉上面的内容,或把文件登记进 NOT_MIRRORED 并写原因', file=sys.stderr)
        return 2
    os.makedirs(MIRROR, exist_ok=True)
    for r in changed + new:
        put(a[r], os.path.join(MIRROR, r))
    for r in extra:
        os.remove(b[r])
    print(f'SNAPSHOT: 文件={len(a)} 更新={len(changed)} 新增={len(new)} 从镜像删除={len(extra)} → {MIRROR}')
    for r in changed: print(f'  更新\t{r}')
    for r in new: print(f'  新增\t{r}')
    for r in extra: print(f'  删除\t{r}')
    return 0


def cmd_restore(args):
    b = manifest(MIRROR, mirror_side=True)
    if not b:
        print(f'🚨 仓库镜像是空的: {MIRROR}', file=sys.stderr); return 2
    if args == ['--missing']:
        todo = [r for r in b if not os.path.lexists(os.path.join(TS, r))]
        for r in todo:
            put(b[r], os.path.join(TS, r))
        print(f'RESTORE: 补齐本机缺的文件={len(todo)} 已有的未动={len(b) - len(todo)}')
        return 0
    if not args or any(x.startswith('-') for x in args):
        print(__doc__, file=sys.stderr); return 2
    bad = [r for r in args if r not in b]
    if bad:
        print(f'🚨 镜像里没有: {" ".join(bad)}', file=sys.stderr); return 2
    for r in args:
        put(b[r], os.path.join(TS, r))
        print(f'  还原\t{r}')
    print(f'RESTORE: 还原={len(args)}(要回到更早的版本:先在仓库里 git checkout <提交> -- scripts/<文件>,再 restore)')
    return 0


def main(a):
    if not a or a[0] == 'status':
        return cmd_status()
    if a[0] == 'snapshot' and len(a) == 1:
        return cmd_snapshot()
    if a[0] == 'restore':
        return cmd_restore(a[1:])
    print(__doc__, file=sys.stderr); return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
