"""Exercise real WebRTC channels between two game documents on localhost."""
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from threading import Thread, Event
import subprocess
import tempfile
import os
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".qa/testdeps"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fakeredis
from api import rooms
store = fakeredis.FakeRedis(decode_responses=True)
rooms.redis = lambda *args: store.execute_command(*args)

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
  await until(()=>h.eval('typeof selectDifficulty')==='function'&&g.eval('typeof selectDifficulty')==='function','load');
  // Local candidates suffice for this test; external STUN/NAT traversal is not tested.
  for(const w of [h,g])w.eval('window.NativeRTC=RTCPeerConnection;window.RTCPeerConnection=class extends NativeRTC{constructor(){super({iceServers:[]})}}');
  for(const w of [h,g])w.eval("window.earlyMusic=false;window.savedStartBgm=startBgm;startBgm=function(){if(race.t<0)window.earlyMusic=true;return savedStartBgm()}");
  h.document.getElementById('onlineBtn').click();g.document.getElementById('onlineBtn').click();
  h.eval("selectDifficulty('hard')");h.document.getElementById('hostBtn').click();
  await until(()=>/^[0-9]{6}$/.test(h.document.getElementById('roomNumber').textContent),'six digit room');
  if(h.eval('mode')!=='menu')throw Error('host started before guest');results.push('PASS host waits in six-digit room');
  g.document.getElementById('joinBtn').click();g.document.getElementById('remoteCode').value=h.document.getElementById('roomNumber').textContent;g.document.getElementById('applyCode').click();
  await until(()=>g.eval('mode')==='guest','automatic shared start');results.push('PASS six digit join, real WebRTC channel and automatic start');
  if(g.eval('race.difficulty')!=='hard'||h.eval('JSON.stringify(race.rocks)')!==g.eval('JSON.stringify(race.rocks)'))throw Error('difficulty or randomized course mismatch');results.push('PASS host difficulty and randomized course match on guest');
  if(h.earlyMusic||g.earlyMusic)throw Error('BGM started during countdown');results.push('PASS countdown leaves BGM stopped on both players');
  await until(()=>h.eval('race.t')>0,'countdown');results.push('PASS shared start and countdown');
  await until(()=>h.eval('bgm.readyState>=2&&!bgm.paused&&bgm.loop')&&g.eval('bgm.readyState>=2&&!bgm.paused&&bgm.loop'),'looping BGM');results.push('PASS both players load and play looping BGM');
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
  if(!h.eval('bgm.paused&&!bgmWanted&&bgm.currentTime===0')||!g.eval('bgm.paused&&!bgmWanted&&bgm.currentTime===0'))throw Error('BGM did not stop on result');results.push('PASS winning and losing results stop and rewind BGM');
  h.document.getElementById('mainBtn').click();await until(()=>g.eval('mode')==='menu','disconnect');results.push('PASS result main-menu button ends opponent session');
 }catch(e){results.push('FAIL '+e.message)}
 document.body.insertAdjacentHTML('beforeend','<pre>'+results.join('\n')+'</pre>');
 await fetch('/result',{method:'POST',body:JSON.stringify(results)});
}
run();
</script>'''

class Handler(rooms.handler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        content_type = 'text/html; charset=utf-8'
        if self.path == '/hold':
            complete.wait(25)
            content = b''
        elif self.path == '/game':
            content = (ROOT / 'index.html').read_bytes()
        elif self.path == '/assets/bgm.wav':
            content = (ROOT / 'assets' / 'bgm.wav').read_bytes()
            content_type = 'audio/wav'
        elif self.path in ['/assets/bgm-loop.js', '/assets/audio-player.js']:
            content = (ROOT / self.path.lstrip('/')).read_bytes()
            content_type = 'application/javascript; charset=utf-8'
        else:
            content = page.encode()
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self):
        if self.path == '/api/rooms':
            return super().do_POST()
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
            '--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--autoplay-policy=no-user-gesture-required',
            '--dump-dom', 'http://127.0.0.1:' + str(server.server_port)],
            capture_output=True, encoding='utf-8', errors='replace', timeout=40)
    print('\n'.join(report) if report else result.stderr[-2000:])
    if not report or any(r.startswith('FAIL') for r in report):
        raise SystemExit(1)
finally:
    complete.set()
    server.shutdown()
    server.server_close()
