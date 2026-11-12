"""Exercise real WebRTC channels between two game documents on localhost."""
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from threading import Thread, Event
import subprocess
import tempfile
import os
import json

ROOT = Path(__file__).resolve().parents[1]
chrome = next((Path(p) for p in [os.environ.get('CHROME_PATH', ''),
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe']
    if p and Path(p).is_file()), None)
if not chrome:
    raise SystemExit('Set CHROME_PATH to Chrome or Edge.')
complete = Event()
report = []
page = r'''<!doctype html><meta charset="utf-8"><title>Online integration check</title>
<iframe id="host" src="/game"></iframe><iframe id="guest" src="/game"></iframe>
<img src="/hold" alt="Waiting for tests">
<script>
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function until(fn,label){for(let i=0;i<150;i++){if(fn())return;await delay(100)}throw Error('Timed out: '+label)}
const results=[];
async function run(){
 try{
  const h=document.getElementById('host').contentWindow,g=document.getElementById('guest').contentWindow;
  await until(()=>h.document.getElementById('soloBtn')&&g.document.getElementById('soloBtn'),'load');
  // Local candidates suffice for this test; external STUN/NAT traversal is not tested.
  for(const w of [h,g])w.eval('window.NativeRTC=RTCPeerConnection;window.RTCPeerConnection=class extends NativeRTC{constructor(){super({iceServers:[]})}}');
  h.document.getElementById('onlineBtn').click();g.document.getElementById('onlineBtn').click();
  h.document.getElementById('hostBtn').click();
  await until(()=>h.document.getElementById('localCode').value,'host offer');
  g.document.getElementById('joinBtn').click();g.document.getElementById('remoteCode').value=h.document.getElementById('localCode').value;g.document.getElementById('applyCode').click();
  await until(()=>g.document.getElementById('localCode').value,'guest answer');
  h.document.getElementById('remoteCode').value=g.document.getElementById('localCode').value;h.document.getElementById('applyCode').click();
  await until(()=>!h.document.getElementById('startOnline').hidden,'data channel');results.push('PASS real offer/answer and data channel');
  h.eval("selectDifficulty('hard')");h.document.getElementById('startOnline').click();await until(()=>g.eval('mode')==='guest','shared start');
  if(g.eval('race.difficulty')!=='hard'||h.eval('JSON.stringify(race.rocks)')!==g.eval('JSON.stringify(race.rocks)'))throw Error('difficulty or randomized course mismatch');results.push('PASS host difficulty and randomized course match on guest');
  await until(()=>h.eval('race.t')>0,'countdown');results.push('PASS shared start and countdown');
  g.eval("input('jump')");await until(()=>h.eval('race.players[1].jump')>0,'guest input');results.push('PASS guest input reaches authoritative host');
  await until(()=>g.eval('race.players[1].jump')>0,'state update');results.push('PASS authoritative state reaches guest');
  if(h.eval('myIndex')!==0||g.eval('myIndex')!==1)throw Error('player indices incorrect');
  results.push('PASS each browser owns its own player');
  h.eval("race.cars=[{id:333,d:race.players[1].d+20,color:CAR_COLORS[2],model:'suv'}]");
  g.eval("input('carDodge')");await until(()=>h.eval('race.players[1].avoidedCars.includes(333)'),'guest car avoidance');
  await until(()=>g.eval('race.players[1].avoidedCars.includes(333)&&race.cars.some(c=>c.id===333)'),'car state');results.push('PASS guest car avoidance and vehicle state synchronize');
  h.eval("race.players[1].d=700;race.players[1].carDodge=0;race.players[1].inv=0;race.buses=[];race.cars=[{id:334,d:700,color:CAR_COLORS[1],model:'sedan'}]");
  await until(()=>g.eval('race.players[1].knockback!==null&&race.players[1].jump>0'),'airborne state');
  await until(()=>g.eval('race.players[1].knockback===null&&race.players[1].d<690'),'landing state');results.push('PASS airborne knockback and landing synchronize');
  h.eval('race.players[1].d=1499.99');await until(()=>g.eval('race.done'),'finish');
  if(g.eval('race.winner')!==1)throw Error('winner mismatch');results.push('PASS shared winning result');
  h.document.getElementById('mainBtn').click();await until(()=>g.eval('mode')==='menu','disconnect');results.push('PASS result main-menu button ends opponent session');
 }catch(e){results.push('FAIL '+e.message)}
 document.body.insertAdjacentHTML('beforeend','<pre>'+results.join('\n')+'</pre>');
 await fetch('/result',{method:'POST',body:JSON.stringify(results)});
}
run();
</script>'''

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == '/hold':
            complete.wait(25)
            content = b''
        elif self.path == '/game':
            content = (ROOT / 'index.html').read_bytes()
        else:
            content = page.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self):
        report.extend(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
        complete.set()
        self.send_response(200)
        self.end_headers()

server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
Thread(target=server.serve_forever, daemon=True).start()
try:
    with tempfile.TemporaryDirectory(prefix='uphill-online-') as profile:
        result = subprocess.run([str(chrome), '--headless', '--disable-gpu', '--no-first-run',
            '--no-default-browser-check', '--user-data-dir=' + profile,
            '--disable-background-timer-throttling', '--disable-renderer-backgrounding',
            '--dump-dom', 'http://127.0.0.1:' + str(server.server_port)],
            capture_output=True, encoding='utf-8', errors='replace', timeout=40)
    print('\n'.join(report) if report else result.stderr[-2000:])
    if not report or any(r.startswith('FAIL') for r in report):
        raise SystemExit(1)
finally:
    complete.set()
    server.shutdown()
    server.server_close()
