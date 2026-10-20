#!/usr/bin/env python3
"""Compile real UI code and render with private files/display; never contacts hardware backends."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--theme', choices=['light','dark'], default='light')
parser.add_argument('--baseline', action='store_true', help='Use source from before the panel polish')
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)

def source(path):
    if args.baseline:
        return subprocess.check_output(['git','-C',str(ROOT),'show','9cb1c70:'+path],text=True)
    return (ROOT/path).read_text()

patch = source('mseries/patches/panel-power-battery-history.patch')
added = '\n'.join(line[1:] for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++'))
start = added.index('public class Power.Widgets.HistoryCard')
end = added.index('\n}\n',start)+3
with tempfile.TemporaryDirectory(prefix='panel-ui-probe-') as directory:
    work=Path(directory)
    (work/'HistoryCard.vala').write_text(added[start:end])
    (work/'Controls.vala').write_text(source('mseries/quick-settings/Controls.vala'))
    command=['valac','--pkg','gtk4','--pkg','granite-7','--pkg','gio-unix-2.0','-X','-lm','-X','-DGETTEXT_PACKAGE="mseries-panel-preview"','-o',str(work/'preview'),str(work/'HistoryCard.vala'),str(work/'Controls.vala'),str(ROOT/'mseries/panel-ui-probes/preview.vala')]
    subprocess.run(command,check=True,stdout=subprocess.DEVNULL)
    cache=work/'cache/mseries-battery';cache.mkdir(parents=True)
    (cache/'summary.txt').write_text('''6 h 20 min left
72% · 8.4 W · based on the last hour
4,5,5,7,8,12,9,8,6,7,8,8
stat\tTypical runtime\t8 h 40 min\tfull charge, 12 runs
stat\tHealth\t94%\tNormal · 82 cycles
stat\tSleep drain\t0.25% / h\tasleep 8 h on battery
run\tToday\t3 h 12 min\t24% used\t7.8 W
app\tWeb browser\t14% CPU
profile\tBalanced\t8.2 W avg\t6 h on battery
event\tPower dropped\t−4.2 W\tDisplay brightness
device\tMouse\t81%\tConnected
tip\tLooking healthy\tYour recent battery use is within its usual range.
''')
    env={**os.environ,'HOME':directory,'XDG_CONFIG_HOME':str(work/'config'),'XDG_CACHE_HOME':str(work/'cache'),'XDG_DATA_HOME':str(work/'data'),'G_DEBUG':'fatal-criticals','GSK_RENDERER':'cairo','GDK_BACKEND':'x11','GTK_THEME':'io.elementary.stylesheet.blueberry'+(':dark' if args.theme=='dark' else '')}
    if args.baseline:env['PANEL_BASELINE']='1'
    for surface in ['quick','battery']:
        subprocess.run(['xvfb-run','-a','-s','-screen 0 1100x1200x24','dbus-run-session','--',str(work/'preview'),surface,str(args.output/f'{surface}-{args.theme}.png')],env=env,check=True,timeout=20)
