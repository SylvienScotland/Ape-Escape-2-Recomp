import re, collections
kz = re.compile(r'\[gpu:kbz\] press (\d+) bbox (\d+),(\d+)-(\d+),(\d+) prim (\d+) test ([0-9a-f]+) alpha ([0-9a-f]+) abe (\d+) z (\d+) (\d+) (\d+) zbp (0x[0-9a-f]+)')
kb = re.compile(r'\[gpu:kb\] press (\d+) burst (\d+) bbox (\d+),(\d+)-(\d+),(\d+) tbp0=(0x[0-9a-f]+) tbw=(\d+) psm=(0x[0-9a-f]+) \d+x\d+ cbp=(0x[0-9a-f]+) cpsm=(\d+) csa=(\d+) tfx=(\d+) rt=(\d+) texhash=([0-9a-f]+) raw=([0-9a-f]+) clut=([0-9a-f]+) serial=(\d+) pageage=(\d+)\.\.(\d+) writer=([0-9a-f]+) mixed=(\d+) clutv=(\d+) epoch=(\d+)')
seq = collections.defaultdict(list)
states = collections.defaultdict(collections.Counter)
tex = collections.Counter(); pages = collections.Counter(); mixedc = collections.Counter()
for line in open('run_tex8.log','r',errors='replace'):
    if '[gpu:kb' not in line: continue
    m = kz.search(line)
    if m:
        b = tuple(m.group(i) for i in range(2,6))
        states[b][(m.group(7),m.group(9))] += 1
        if len(seq[b]) < 14:
            seq[b].append((m.group(7), m.group(9), m.group(10), m.group(11), m.group(12), m.group(13)))
        continue
    m = kb.search(line)
    if m:
        b = tuple(m.group(i) for i in range(3,7))
        tex[(m.group(15), m.group(9))] += 1
        pages[(m.group(19), m.group(20))] += 1
        mixedc[m.group(22)] += 1
print('== keyboard-format textures (texhash, psm) ==')
for k,v in tex.most_common(6): print('   texhash', k[0], 'psm', k[1], v)
print('\n== pageage (written_at..now) top 6 ==')
for k,v in pages.most_common(6): print('   ', k[0]+'..'+k[1], v)
print('\n== mixed flag ==', dict(mixedc))
print('\n== distinct bboxes', len(states), '| with 2+ draw states', sum(1 for s in states.values() if len({k[0] for k in s})>1))
print('\n== per-frame interleave for the 3 tightest double-drawn bboxes ==')
tight = sorted(((b,s) for b,s in states.items() if len(s)==2),
               key=lambda kv: (int(kv[0][2])-int(kv[0][0]))*(int(kv[0][3])-int(kv[0][1])))[:3]
for b,s in tight:
    print(f'\n  bbox {b}  area {(int(b[2])-int(b[0]))*(int(b[3])-int(b[1]))}px  states {dict(s)}')
    for r in seq[b]:
        print('     test=%s abe=%s z=%s %s %s zbp=%s' % r)
