#!/usr/bin/env python3
"""Check real rendered displacement, endpoint restoration and state commits."""
import json
from pathlib import Path
import re
import sys
from PIL import Image
root = Path(sys.argv[1])
def boxes(name):
    im = Image.open(root / (name + '.png')).convert('RGB')
    result = {}
    for color in ['red', 'blue']:
        coords = []
        for y in range(0, im.height, 4):
            for x in range(0, im.width, 4):
                r,g,b = im.getpixel((x,y))
                if (r > 150 and r > g*1.8 and r > b*1.8) if color == 'red' else (b > 150 and b > r*1.8 and b > g*1.8):
                    coords.append((x,y))
        if coords:
            result[color] = [min(x for x,y in coords), min(y for x,y in coords), max(x for x,y in coords), max(y for x,y in coords)]
    return result
names = ['workspace-start','workspace-half','workspace-complete','workspace-cancel','workspace-edge','overview-start','overview-half','overview-complete','overview-close-half','overview-closed']
receipts = {name: boxes(name) for name in names}
start = receipts['workspace-start']
assert len(start) == 1, start
source = next(iter(start))
target = 'red' if source == 'blue' else 'blue'
assert set(receipts['workspace-half']) == {'red','blue'}, receipts
assert set(receipts['workspace-complete']) == {target}, receipts
assert receipts['workspace-cancel'] == start, receipts
assert 0 < receipts['workspace-edge'][source][0] - start[source][0] < 100, receipts
assert set(receipts['overview-complete']) == {'red','blue'}, receipts
# The front window remains unoccluded while thumbnails separate; the rear
# thumbnail is partially occluded halfway through and cannot be width-compared.
front = next(iter(receipts['overview-start']))
half = receipts['overview-half'][front]
end = receipts['overview-complete'][front]
assert half[2] - half[0] > end[2] - end[0] > 0, receipts
left, right = sorted(receipts['overview-complete'].values())
assert left[2] < right[0], receipts
assert receipts['overview-closed'] == receipts['overview-start'], receipts
states = re.findall(r'gesture probe status workspace=(\d+) overview=(true|false) preview=(true|false) windows=(\d+)', (root/'compositor.log').read_text())
assert [(s[0],s[1],s[2]) for s in states] == [
    ('0','false','false'), ('1','false','false'), ('0','false','false'),
    ('0','false','false'), ('0','false','false'), ('0','true','false'),
    ('0','true','false'), ('0','false','false'), ('0','false','false'), ('1','false','false')], states
(root/'measurements.json').write_text(json.dumps({'boxes':receipts,'states':states}, indent=2)+'\n')
print('PASS: workspace displacement, cancellation, edges, overview scale/restore and interrupted spring')
