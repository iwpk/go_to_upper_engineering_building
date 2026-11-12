"""Dependency-free Chrome headless checks. Run: python tests/check_browser.py"""
from pathlib import Path
import os
import subprocess
import tempfile
import html
import re

ROOT = Path(__file__).resolve().parents[1]
chrome = next((Path(p) for p in [
    os.environ.get('CHROME_PATH', ''),
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
] if p and Path(p).is_file()), None)
if not chrome:
    raise SystemExit('Set CHROME_PATH to a Chrome or Edge executable.')
test_js = r'''
const results=[];
function check(name,fn){try{fn();results.push('PASS '+name)}catch(e){results.push('FAIL '+name+': '+e.message)}}
function assert(v,msg='assertion failed'){if(!v)throw Error(msg)}
function fresh(){mode='solo';myIndex=0;race=newRace(1,'normal',12345);race.t=0;race.nextBus=999;race.nextCar=999;paused=false;}
check('exact route and previous-stop boundaries',()=>{
 assert(STOPS.map(s=>s.d).join(',')==='0,50,650,900,1200,1500');
 for(const [d,want] of [[30,0],[50,0],[51,50],[650,50],[651,650],[900,650],[901,900],[1201,1200]])assert(previousStop(d).d===want,'stop at '+d);
});
check('automatic movement and jumping',()=>{fresh();step(.5);assert(race.players[0].d===6);action(race.players[0],'jump');step(.1);assert(race.players[0].jump>0)});
check('keyboard works immediately after start click',()=>{$('soloBtn').focus();$('soloBtn').click();race.t=0;document.body.dispatchEvent(new KeyboardEvent('keydown',{code:'Space',bubbles:true}));assert(race.players[0].jump>0)});
check('rock collision versus jump clearance',()=>{fresh();let p=race.players[0];p.d=94.9;step(STEP);assert(p.stun===1);fresh();p=race.players[0];p.d=94.9;p.jump=5;step(STEP);assert(p.stun===0)});
check('bus takes player to nearest earlier stop and clears hazards',()=>{fresh();let p=race.players[0];const future=race.rocks.findIndex(r=>r.d>700);p.d=700;p.hits=[1,future];race.buses=[{id:0,d:700}];step(STEP);assert(p.ride===650);for(let i=0;i<60;i++)step(STEP);assert(p.ride===null&&p.d>=650&&p.d<660);assert(!p.hits.includes(future));assert(p.inv>0)});
check('right-arrow avoids bus without cooldown, jump does not',()=>{fresh();let p=race.players[0];p.d=700;race.buses=[{id:0,d:700}];action(p,'dodge');step(STEP);assert(p.ride===null);action(p,'dodge');assert(p.dodge===.9);fresh();p=race.players[0];p.d=700;p.jump=10;race.buses=[{id:0,d:700}];step(STEP);assert(p.ride===650)});
check('avoided bus stays safe after release; other buses still collide',()=>{fresh();let p=race.players[0];p.d=700;race.buses=[{id:8,d:715,route:'5513'}];action(p,'dodge');assert(p.avoidedBuses.includes(8));p.dodge=0;race.buses[0].d=700;step(STEP);assert(p.ride===null);race.buses.push({id:9,d:p.d,route:'5516'});step(STEP);assert(p.ride===650&&p.rideRoute==='5516')});
check('avoidance belongs to each player',()=>{race=newRace(2);race.t=0;race.nextBus=999;race.players.forEach(p=>p.d=700);race.buses=[{id:1,d:700}];action(race.players[0],'dodge');step(STEP);assert(race.players[0].ride===null&&race.players[1].ride===650)});
check('two bus routes repeat in sequence',()=>{fresh();const routes=[];for(let i=0;i<3;i++){race.buses=[];race.nextBus=race.t;step(STEP);routes.push(race.buses.at(-1).route)}assert(routes.join(',')==='5513,5516,5513')});
check('left arrow avoids cars permanently and right arrow does not',()=>{fresh();let p=race.players[0];p.d=700;race.cars=[{id:1,d:715,color:CAR_COLORS[0],model:'sedan'}];document.body.dispatchEvent(new KeyboardEvent('keydown',{code:'ArrowLeft',bubbles:true}));assert(p.avoidedCars.includes(1));p.carDodge=0;race.cars[0].d=700;step(STEP);assert(p.knockback===null);action(p,'carDodge');step(STEP);action(p,'carDodge');assert(p.carDodge===.9);fresh();p=race.players[0];p.d=700;race.cars=[{id:1,d:700,color:CAR_COLORS[0],model:'sedan'}];action(p,'dodge');step(STEP);assert(p.knockback!==null&&p.stun===0&&p.ride===null)});
check('jump cannot avoid car and left arrow cannot avoid bus',()=>{fresh();let p=race.players[0];p.d=700;p.jump=9;race.cars=[{id:1,d:700,color:CAR_COLORS[0],model:'suv'}];step(STEP);assert(p.knockback!==null);fresh();p=race.players[0];p.d=700;race.buses=[{id:1,d:700}];action(p,'carDodge');step(STEP);assert(p.ride===650)});
check('car launches an arc and lands exactly 30 meters back',()=>{fresh();const p=race.players[0];p.d=700;race.cars=[{id:1,d:700,color:CAR_COLORS[0],model:'sedan'}];step(STEP);const from=p.d;step(FLIGHT_TIME/2);assert(Math.abs(p.d-(from-15))<.001&&p.jump>35);const height=p.jump;action(p,'jump');action(p,'carDodge');assert(p.jump===height&&p.carDodge===0);race.buses=[{id:1,d:p.d}];step(STEP);assert(p.ride===null);step(FLIGHT_TIME);assert(p.knockback===null&&p.jump===0&&Math.abs(p.d-(from-30))<.001&&p.inv===1);step(STEP);assert(p.d>from-30)});
check('car flight clamps at start and time keeps running',()=>{fresh();const p=race.players[0];p.d=10;race.cars=[{id:1,d:10,color:CAR_COLORS[0],model:'suv'}];step(STEP);step(FLIGHT_TIME);assert(p.d===0&&p.knockback===null&&race.t>1);fresh();race.t=180.9;race.players[0].knockback={from:700,to:670,elapsed:0,startJump:0};step(.2);assert(race.done&&race.winner===null)});
check('switching avoidance preserves earlier vehicle immunity',()=>{fresh();const p=race.players[0];p.d=700;race.buses=[{id:1,d:715}];action(p,'dodge');race.cars=[{id:2,d:715,color:CAR_COLORS[2],model:'suv'}];action(p,'carDodge');assert(p.avoidedBuses.includes(1)&&p.avoidedCars.includes(2));race.buses[0].d=race.cars[0].d=700;step(STEP);assert(p.ride===null&&p.stun===0)});
check('all eight car model and color combinations spawn',()=>{fresh();const combos=new Set();for(let i=0;i<8;i++){race.cars=[];assert(spawnTraffic('car'));const c=race.cars[0];combos.add(c.model+c.color)}assert(combos.size===8)});
check('traffic spacing survives two racers, stops and bus returns',()=>{race=newRace(2);race.t=0;race.players[1].d=120;let sawBus=false,sawCar=false;for(let i=0;i<10000&&!race.done;i++){step(STEP);sawBus ||= race.buses.length>0;sawCar ||= race.cars.length>0;const traffic=[...race.buses,...race.cars];for(let a=0;a<traffic.length;a++)for(let b=a+1;b<traffic.length;b++)assert(Math.abs(traffic[a].d-traffic[b].d)>=trafficGap()-.001,'unsafe traffic spacing')}assert(sawBus&&sawCar);assert(Math.abs((trafficGap()-BUS_CONTACT-CAR_CONTACT)/(SPEED+CAR_SPEED)-DIFFICULTIES[race.difficulty].reaction)<.001)});
check('camera shows exactly 30 meters in each direction',()=>{fresh();race.players[0].d=700;render(0);assert(Math.abs(sx(670))<.001);assert(Math.abs(sx(700)-W/2)<.001);assert(Math.abs(sx(730)-W)<.001)});
check('random courses vary but preserve jump safety on all difficulties',()=>{for(const difficulty of Object.keys(DIFFICULTIES)){let early=0,late=0;for(let seed=1;seed<=20;seed++){const items=makeRocks(difficulty,seed);for(let i=1;i<items.length;i++)assert((items[i].d-items[i-1].d)/SPEED>=2*JUMP_SPEED/GRAVITY+DIFFICULTIES[difficulty].recovery);early+=items.filter(r=>r.d<500).length;late+=items.filter(r=>r.d>=1000).length}assert(late>early);assert(JSON.stringify(makeRocks(difficulty,1))!==JSON.stringify(makeRocks(difficulty,2)))}assert(JSON.stringify(makeRocks('normal',123))===JSON.stringify(makeRocks('normal',123)))});
check('all difficulty courses are jumpable without collisions',()=>{for(const difficulty of Object.keys(DIFFICULTIES))for(const seed of [1,19,101]){fresh();race=newRace(1,difficulty,seed);race.t=0;race.nextBus=race.nextCar=999;const p=race.players[0];for(let i=0;i<9000&&!race.done;i++){const next=race.rocks.find(r=>r.d>p.d);if(next&&next.d-p.d<=4&&p.jump===0)action(p,'jump');step(STEP);assert(p.stun===0,'unavoidable obstacle at '+p.d+' '+difficulty)}assert(race.done&&race.winner===0)}});
check('random traffic is denser and cars outnumber buses',()=>{for(const difficulty of Object.keys(DIFFICULTIES)){race=newRace(1,difficulty,12345);race.t=0;race.players[0].inv=999;for(let i=0;i<7200&&!race.done;i++)step(STEP);assert(race.busId>=8,'buses postponed');assert(race.carId>=race.busId*2,'not enough cars');const samples=new Set(Array.from({length:10},()=>carInterval().toFixed(3)));assert(samples.size>5)}});
check('result menu uses minutes and seconds and routes back to main',()=>{selectDifficulty('hard');mode='solo';start(1);race.players[0].finish=159.73;race.winner=0;race.done=true;endScreen();assert($('panelTitle').textContent==='무사히 도착했다!'&&$('panelText').textContent==='02:39.73','finish title or clock: '+$('panelTitle').textContent+' '+$('panelText').textContent);assert($('onlineBtn').hidden&&!$('mainBtn').hidden&&$('difficultyPicker').hidden&&$('helpBtn').hidden,'result buttons');$('mainBtn').click();assert(mode==='menu'&&!$('difficultyPicker').hidden&&!$('onlineBtn').hidden&&$('mainBtn').hidden,'main buttons');$('soloBtn').click();assert(race.difficulty==='hard','replay difficulty '+race.difficulty);race.done=true;race.winner=null;endScreen();assert($('panelTitle').textContent==='수업에 지각했다!'&&$('panelText').hidden&&$('panelFlag').hidden,'game over panel '+$('panelTitle').textContent);selectDifficulty('normal');menu()});
check('finish and time limit',()=>{fresh();race.players[0].d=1499.9;step(STEP);assert(race.done&&race.winner===0);fresh();race.t=180.99;step(STEP);assert(race.done&&race.winner===null&&race.t===181)});
check('online second-player victory and independent camera',()=>{race=newRace(2);race.t=0;race.nextBus=999;race.players[1].d=1499.9;step(STEP);assert(race.winner===1);myIndex=0;render(1);let firstCam=cam;myIndex=1;render(1);assert(cam-firstCam>4000);assert(validState(race))});
check('invalid connection code rejected',()=>{let failed=false;try{decode('not a code')}catch{failed=true}assert(failed)});
check('expert reaction gap is 0.25 seconds and selectable',()=>{selectDifficulty('expert');mode='solo';start(1);assert(race.difficulty==='expert');assert(Math.abs((trafficGap()-BUS_CONTACT-CAR_CONTACT)/(SPEED+BUS_SPEED)-.25)<.001);selectDifficulty('normal');menu()});
check('route markers align with stops and update for local identity and retreat',()=>{fresh();STOPS.forEach((s,i)=>assert(Math.abs(routePosition(s.d)-i*20)<.001));assert(routePosition(-30)===0&&routePosition(1600)===100);updateHud();assert($('routeRival').hidden);race=newRace(2);race.players[0].d=650;race.players[1].d=900;myIndex=1;updateHud();assert(parseFloat($('routeMe').style.left)===60&&parseFloat($('routeRival').style.left)===40&&!$('routeRival').hidden);race.players[1].d=650;updateHud();assert($('routeMe').style.top!==$('routeRival').style.top);race.players[1].d=620;updateHud();assert(parseFloat($('routeMe').style.left)<40);myIndex=0});
check('avoided cars cover runners until fully passed; cars cover all buses',()=>{fresh();const p=race.players[0];p.d=700;race.cars=[{id:1,d:720,color:CAR_COLORS[0],model:'sedan'}];action(p,'carDodge');p.carDodge=0;assert(behindCars(p));const saved={human,car,bus};let calls=[];try{human=(x,y,color)=>calls.push(color);car=()=>calls.push('car');bus=()=>calls.push('bus');race.buses=[{id:2,d:700}];render(0);assert(calls.indexOf('bus')<calls.indexOf('car'));assert(calls.indexOf('#347cdb')<calls.indexOf('car'));race.cars[0].d=690;assert(!behindCars(p));calls=[];render(0);assert(calls.indexOf('car')<calls.indexOf('#347cdb'));p.ride=650;calls=[];render(0);assert(calls.lastIndexOf('bus')<calls.indexOf('car'));}finally{human=saved.human;car=saved.car;bus=saved.bus}});
check('overlapping players keep local runner in front while avoiding cars',()=>{race=newRace(2);race.t=0;mode='solo';myIndex=0;race.players.forEach(p=>p.d=700);race.cars=[{id:1,d:700,color:CAR_COLORS[0],model:'sedan'}];action(race.players[0],'carDodge');const saved={human,car};const calls=[];try{human=(x,y,color)=>calls.push(color);car=()=>calls.push('car');render(0);assert(calls.indexOf('#dd6459')<calls.indexOf('#347cdb')&&calls.indexOf('#347cdb')<calls.indexOf('car'))}finally{human=saved.human;car=saved.car}});
check('minimal menu and large countdown show 3 2 1 then disappear',()=>{menu();assert($('panelTitle').textContent==='윗공대 오르기'&&$('panelFlag').hidden&&$('panelText').hidden);mode='solo';start(1);for(const [time,want] of [[-3,'3'],[-2,'2'],[-1,'1']]){race.t=time;updateHud();assert(!$('countdown').hidden&&$('countdown').textContent===want)}race.t=0;updateHud();assert($('countdown').hidden)});
check('settings hide control hints but preserve collision notices',()=>{fresh();race.players[0].d=700;race.cars=[{id:3,d:720,color:CAR_COLORS[0],model:'sedan'}];$('settingsBtn').click();assert(paused&&$('settingsDialog').open);$('hintsToggle').checked=false;$('hintsToggle').dispatchEvent(new Event('change'));$('settingsDialog').close();paused=false;updateHud();assert($('status').textContent==='');race.players[0].knockback={from:700,to:670,elapsed:.2,startJump:0};updateHud();assert($('status').textContent!=='');race.players[0].knockback=null;$('hintsToggle').checked=true;$('hintsToggle').dispatchEvent(new Event('change'));updateHud();assert($('status').textContent.includes('←'))});
fresh();mode='menu';menu();render(0);updateHud();
const out=document.createElement('pre');out.id='qa-results';out.textContent=results.join('\n');document.body.append(out);
'''
qa = ROOT / '.qa'
qa.mkdir(exist_ok=True)
source = (ROOT / 'index.html').read_text(encoding='utf-8')
source = source.replace('<script>', '<script>window.requestAnimationFrame=()=>0;</script><script>', 1)
source = source.replace('</script></body>', test_js + '</script></body>')
scene = os.environ.get('QA_SCENE')
if scene is not None:
    distance = float(scene)
    source = source.replace('fresh();mode=\'menu\';menu();render(0);updateHud();',
        f"fresh();race.players[0].d={distance};$('overlay').hidden=true;render(0);updateHud();")
testfile = qa / 'checks.html'
testfile.write_text(source, encoding='utf-8')
with tempfile.TemporaryDirectory(prefix='uphill-browser-') as profile:
    result = subprocess.run([str(chrome), '--headless', '--disable-gpu', '--no-first-run',
        '--no-default-browser-check', '--allow-file-access-from-files',
        '--user-data-dir=' + profile, '--dump-dom', '--timeout=10000',
        '--screenshot=' + str(qa / (('scene-' + scene + '.png') if scene else 'preview.png')), '--window-size=' + os.environ.get('QA_VIEWPORT', '1440,1100'),
        testfile.as_uri()], capture_output=True, encoding='utf-8', errors='replace', timeout=35)
    match = re.search(r'<pre id="qa-results">(.*?)</pre>', result.stdout, re.S)
    if not match:
        print(result.stderr[-2500:])
        raise SystemExit('Browser did not produce test results.')
    report = html.unescape(match.group(1))
    print(report)
    if 'FAIL' in report:
        raise SystemExit(1)
print('Screenshot: .qa/' + (('scene-' + scene + '.png') if scene else 'preview.png'))
