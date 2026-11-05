import re, collections
kz = re.compile(r'\[gpu:kbz\] press (\d+) bbox (\d+),(\d+)-(\d+),(\d+) prim (\d+) test ([0-9a-f]+) alpha ([0-9a-f]+) abe (\d+) z (\d+) (\d+) (\d+)')
kb = re.compile(r'\[gpu:kb\] press (\d+) burst (\d+) bbox (\d+),(\d+)-(\d+),(\d+) tbp0=(0x[0-9a-f]+) tbw=(\d+) psm=(0x[0-9a-f]+) \d+x\d+ cbp=(0x[0-9a-f]+) cpsm=(\d+) csa=(\d+) tfx=(\d+) rt=(\d+) texhash=([0-9a-f]+)')
op = collections.defaultdict(collections.Counter); bl = collections.defaultdict(collections.Counter)
tex = collections.defaultdict(collections.Counter)
for line in open('run_tex8.log','r',errors='replace'):
    if '[gpu:kb' not in line: continue
    m = kz.search(line)
    if m:
        b = tuple(m.group(i) for i in range(2,6)); zt = (m.group(10),m.group(11),m.group(12))
        (bl if m.group(9)=='1' else op)[b][zt] += 1
        continue
    m = kb.search(line)
    if m: tex[tuple(m.group(i) for i in range(3,7))][m.group(15)] += 1
both = set(op) & set(bl)
same = [b for b in both if set(op[b]) == set(bl[b])]
diff = [b for b in both if set(op[b]) != set(bl[b])]
area = lambda b: (int(b[2])-int(b[0]))*(int(b[3])-int(b[1]))
print('bboxes drawn in BOTH states:', len(both))
print('   exact same z-set  (pure duplicate):', len(same))
print('   different z       (overlapping geom):', len(diff))
kbpix = [b for b in same if '69b7178e' in tex.get(b,{})]
print('\n== keyboard-atlas (69b7178e) bboxes in the pure-duplicate class:', len(kbpix), '==')
for b in sorted(kbpix, key=area, reverse=True)[:6]:
    print(f'   bbox {b} area {area(b)}px  opaque x{sum(op[b].values())} blended x{sum(bl[b].values())}  z={list(op[b])[0]}')
print('\n== largest pure duplicates overall (any atlas) ==')
for b in sorted(same, key=area, reverse=True)[:6]:
    th = dict(tex.get(b,{}))
    print(f'   bbox {b} area {area(b)}px  opaque x{sum(op[b].values())} blended x{sum(bl[b].values())} z={list(op[b])[0]}  tex={th}')
print('\n== largest DIFFERENT-z pairs (overlapping geometry, not duplicates) ==')
for b in sorted(diff, key=area, reverse=True)[:4]:
    print(f'   bbox {b} area {area(b)}px  opaque x{sum(op[b].values())} blended x{sum(bl[b].values())}')
    print('      opaque z-set :', list(op[b])[:2])
    print('      blended z-set:', list(bl[b])[:2])
