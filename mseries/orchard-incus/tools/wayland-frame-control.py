"""Continuous-damage GTK control window for a real Wayland timing comparison."""
import sys,json,time,statistics,argparse
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('--source',required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
sys.path.insert(0,args.source)
from orchard_incus.app import App
from gi.repository import Gtk,Gdk,GLib
app=App();app.set_application_id('io.github.techmore.OrchardWaylandControl');app.register(None)
win=Gtk.ApplicationWindow(application=app,title='GTK Wayland frame timing control',default_width=1024,default_height=740)
box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);box.append(Gtk.Label(label='GTK timing control',vexpand=True));label=Gtk.Label();box.append(label);win.set_child(box);win.present()
loop=GLib.MainLoop();timings=[];tick=0;count=0

def begin():
 global tick
 clock=win.get_frame_clock();clock.connect('after-paint',lambda c:timings.append(c.get_current_timings()))
 def frame(w,c):
  global count
  count+=1;label.set_text('Wayland frame pacing · '+str(count));return True
 tick=win.add_tick_callback(frame)
 GLib.timeout_add(6000,stop);return False

def stop():
 win.remove_tick_callback(tick);GLib.timeout_add(600,done);return False

def done():
 x=[t for t in timings if t and t.get_complete() and t.get_presentation_time()>0]
 lat=sorted((t.get_presentation_time()-t.get_frame_time())/1000 for t in x)
 ps=sorted(set(t.get_presentation_time() for t in x));gaps=sorted((b-a)/1000 for a,b in zip(ps,ps[1:]))
 def stats(v):return {'p50':statistics.median(v),'p95':v[int(.95*(len(v)-1))],'max':max(v)}
 r={'display':type(win.get_display()).__name__,'renderer':type(win.get_renderer()).__name__,'frames':len(x),'frame_start_to_presentation_ms':stats(lat),'presentation_gap_ms':stats(gaps)}
 args.output.write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True)
 win.close();loop.quit();return False
GLib.timeout_add(500,begin);loop.run()
