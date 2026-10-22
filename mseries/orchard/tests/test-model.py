import http.server
import json
import os
import subprocess
import sys
import threading
seen = set()
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def send_json(self, value, status=200):
        body=json.dumps(value).encode();self.send_response(status)
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        assert 'Authorization' not in self.headers
        if self.path=='/v1/models':
            seen.add('models');self.send_json({'data':[{'id':'fixture-model'}]})
        elif self.path=='/auth/models':
            seen.add('auth');self.send_json({'error':'unauthorized'},401)
        else: raise AssertionError(self.path)
    def do_POST(self):
        assert self.path=='/v1/chat/completions'
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        assert body=={'model':'fixture-model','messages':[{'role':'user','content':'quoted"prompt\nline'}],'stream':False}
        seen.add('chat');self.send_json({'choices':[{'message':{'content':'fixture answer'}}]})
with http.server.HTTPServer(('127.0.0.1',0),Handler) as server:
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    result=subprocess.run(sys.argv[1:],env={**os.environ,'ORCHARD_MODEL_TEST_URL':f'http://127.0.0.1:{server.server_port}'},timeout=20)
    server.shutdown()
    assert result.returncode==0,result.returncode
    assert seen=={'models','auth','chat'},seen
