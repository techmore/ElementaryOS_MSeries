"""Protocol-level tests: only a disposable Unix socket is contacted."""
import http.server
import json
import os
from pathlib import Path
import socketserver
import subprocess
import sys
import tempfile
import threading

seen = set()
backup_path = None
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def respond(self, value, status=200, etag=None):
        body = value if isinstance(value, bytes) else json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Length', str(len(body)))
        if etag: self.send_header('ETag', etag)
        self.end_headers(); self.wfile.write(body)
    def payload(self): return json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
    def operation(self, name='success'):
        self.respond({'type':'async','operation':'/1.0/operations/'+name})
    def do_GET(self):
        global backup_path
        if self.path == '/1.0/instances/test':
            self.respond({'type':'sync','metadata':{'name':'test','config':{},'devices':{}}},etag='"one"')
        elif self.path.startswith('/1.0/operations/'):
            code = 400 if '/fail/' in self.path else 200
            self.respond({'type':'sync','metadata':{'status_code':code,'err':'intentional failure' if code==400 else ''}})
        elif backup_path and self.path == backup_path+'/export':
            seen.add('download');self.respond(b'fixture-backup-contents')
        elif self.path == '/1.0/instances/test/logs/empty.log':
            seen.add('empty-log');self.respond(b'')
        elif self.path == '/1.0/instances/test/logs/lxc.log':
            seen.add('logs');self.respond(b'fixture log\n')
        else: self.respond({'type':'error','error':'unexpected GET '+self.path},404)
    def do_PATCH(self):
        assert self.path == '/1.0/instances/test'
        assert self.payload()['config']['user.note'] == 'quote" slash\\ newline\nvalue'
        if self.headers['If-Match'] == '"stale"':
            seen.add('conflict');self.respond({'type':'error','error':'ETag mismatch'},412)
        else:
            assert self.headers['If-Match'] == '"one"';seen.add('config');self.operation()
    def do_POST(self):
        global backup_path
        body=self.payload()
        if self.path == '/1.0/instances':
            if body['name']=='new':
                assert body['config']['limits.cpu']=='2' and body['ephemeral'] is True
                assert body['source']['alias']=='alpine/edge' and body['source']['protocol']=='simplestreams'
                seen.add('create')
            elif body['name']=='sandbox':
                assert body['profiles']==[] and body['type']=='virtual-machine'
                assert body['source']=={'type':'image','fingerprint':'cached-fingerprint'}
                assert body['devices']=={'root':{'type':'disk','path':'/','pool':'fixture'}}
                seen.add('sandbox')
            else:
                assert body=={'name':'copy','source':{'type':'copy','source':'test'}};seen.add('clone')
        elif self.path == '/1.0/instances/test/snapshots':
            assert body['name']=='quoted"snapshot';seen.add('snapshot')
        elif self.path == '/1.0/instances/test/backups':
            assert body['name'].startswith('orchard-export-') and body['expires_at'].endswith('Z')
            backup_path=self.path+'/'+body['name'];seen.add('backup')
        else: raise AssertionError(self.path)
        self.operation()
    def do_PUT(self):
        body=self.payload()
        if self.path.endswith('/state'):
            assert body['action']=='stop' and body['force'] is True;seen.add('failure');self.operation('fail')
        else:
            assert body=={'restore':'quoted"snapshot'};seen.add('restore');self.operation()
    def do_DELETE(self):
        assert self.path==backup_path;seen.add('cleanup');self.respond({'type':'sync'})
with tempfile.TemporaryDirectory(prefix='orchard-client-') as directory:
    path=str(Path(directory)/'incus.socket')
    with socketserver.UnixStreamServer(path,Handler) as server:
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        result=subprocess.run(sys.argv[1:],env={**os.environ,'INCUS_SOCKET':path,'ORCHARD_TEST_ARCHIVE':str(Path(directory)/'backup.tar.gz')},timeout=20)
        server.shutdown()
    assert result.returncode==0,result.returncode
    assert seen=={'config','conflict','create','sandbox','clone','snapshot','restore','failure','backup','download','cleanup','logs','empty-log'},seen
