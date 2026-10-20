import http.server
import json
import os
from pathlib import Path
import socketserver
import subprocess
import sys
import tempfile
import threading
if not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
    sys.exit(77)
state={'status':'Stopped','memory':{'usage':0},'cpu':{'usage':0},'network':{},'disk':{}}
instance={'name':'fixture-with-a-long-name-that-must-not-widen-the-window','type':'container','status':'Stopped','architecture':'aarch64','description':'Fixture','ephemeral':False,'profiles':['default'],'config':{},'expanded_config':{},'devices':{},'expanded_devices':{},'state':state}
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):pass
    def do_GET(self):
        if self.path=='/1.0/instances?recursion=2':data=[instance]
        elif self.path=='/1.0/instances/fixture':data=instance
        elif self.path=='/1.0/instances/fixture/state':data=state
        elif self.path=='/1.0':data={'api_version':'1.0','environment':{'server_version':'fixture','kernel':'Linux','os_name':'fixture'}}
        elif self.path=='/1.0/resources':data={'memory':{'total':1073741824},'cpu':{'total':2}}
        elif self.path=='/1.0/instances/fixture/logs/lxc.log':
            body=b'fixture log\n';self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
        elif self.path.endswith('?recursion=1'):data=[]
        else:raise AssertionError(self.path)
        body=json.dumps({'type':'sync','metadata':data}).encode()
        self.send_response(200);self.send_header('ETag','"fixture"');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
with tempfile.TemporaryDirectory(prefix='orchard-ui-') as directory:
    path=str(Path(directory)/'incus.socket')
    with socketserver.UnixStreamServer(path,Handler) as server:
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        env={**os.environ,'INCUS_SOCKET':path,'XDG_CONFIG_HOME':directory+'/config','XDG_STATE_HOME':directory+'/state','G_DEBUG':'fatal-criticals'}
        result=subprocess.run(sys.argv[1:],env=env,timeout=20)
        server.shutdown()
        assert result.returncode==0,result.returncode
