import http.server
import json
import os
from pathlib import Path
import socketserver
import subprocess
import sys
import tempfile
import threading
stopped=set();updated=set();started=set()
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):pass
    def respond(self,value,etag=None):
        body=json.dumps(value).encode();self.send_response(200)
        self.send_header('Content-Length',str(len(body)))
        if etag:self.send_header('ETag',etag)
        self.end_headers();self.wfile.write(body)
    def payload(self):return json.loads(self.rfile.read(int(self.headers['Content-Length'])))
    def do_GET(self):
        if self.path.startswith('/1.0/operations/'):
            self.respond({'type':'sync','metadata':{'status_code':200}});return
        name=self.path.split('/')[-1]
        assert name in {'success','stale','race','ephemeral'}
        config={'user.keep':'original','volatile.last_state.power':'STOPPED' if name in stopped else 'RUNNING'}
        if name=='race' and name in stopped:config['user.keep']='someone-else-edited'
        etag='"fresh"' if name=='stale' else '"after"' if name in stopped else '"before"'
        self.respond({'type':'sync','metadata':{'status':'Stopped' if name in stopped else 'Running','config':config,'ephemeral':name=='ephemeral'}},etag)
    def do_PUT(self):
        name=self.path.split('/')[-2];body=self.payload()
        assert name in {'success','race'},'Unsafe lifecycle request: '+name
        if body['action']=='stop':stopped.add(name)
        else:assert name=='success' and name in updated;started.add(name)
        self.respond({'type':'async','operation':'/1.0/operations/ok'})
    def do_PATCH(self):
        name=self.path.split('/')[-1]
        assert name=='success' and self.headers['If-Match']=='"after"'
        assert self.payload()=={'config':{'limits.memory':'256MiB'}}
        updated.add(name);self.respond({'type':'async','operation':'/1.0/operations/ok'})
with tempfile.TemporaryDirectory(prefix='orchard-restart-') as directory:
    path=str(Path(directory)/'incus.socket')
    with socketserver.UnixStreamServer(path,Handler) as server:
        threading.Thread(target=server.serve_forever,daemon=True).start()
        result=subprocess.run(sys.argv[1:],env={**os.environ,'INCUS_SOCKET':path,'XDG_CONFIG_HOME':directory+'/config'},timeout=20)
        server.shutdown();assert result.returncode==0,result.returncode
    assert stopped=={'success','race'} and updated=={'success'} and started=={'success'},(stopped,updated,started)
