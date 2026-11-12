"""Short-lived WebRTC signaling rooms. Redis is shared across Vercel instances."""
import hashlib
import json
import os
import re
import secrets
from http.server import BaseHTTPRequestHandler
from urllib.request import Request, urlopen

TTL = 300


class RoomError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def redis(*command):
    url = os.environ.get('UPSTASH_REDIS_REST_URL') or os.environ.get('KV_REST_API_URL')
    token = os.environ.get('UPSTASH_REDIS_REST_TOKEN') or os.environ.get('KV_REST_API_TOKEN')
    if not url or not token:
        raise RoomError(503, '방 서버 설정이 필요합니다. 관리자에게 문의해주세요.')
    req = Request(url, json.dumps(command).encode(), {
        'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    with urlopen(req, timeout=8) as response:
        data = json.load(response)
    if 'error' in data:
        raise RoomError(503, '방 서버에 연결하지 못했어요. 잠시 후 다시 시도해주세요.')
    return data.get('result')


# Authentication and mutation run atomically: only one guest can claim a room.
ROOM_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then return cjson.encode({error=404}) end
local r = cjson.decode(raw)
local action, token = ARGV[1], ARGV[2]
local function save()
  redis.call('SET', KEYS[1], cjson.encode(r), 'KEEPTTL')
end
if action == 'join' then
  if r.guest and r.guest ~= token then return cjson.encode({error=409}) end
  r.guest = token; save()
  return cjson.encode({offer=r.offer})
end
if token ~= r.owner and token ~= r.guest then return cjson.encode({error=403}) end
if action == 'poll' then
  return cjson.encode({answer=r.answer, joined=r.guest ~= nil})
elseif action == 'answer' and token == r.guest then
  r.answer = cjson.decode(ARGV[3]); save()
  return cjson.encode({ok=true})
elseif action == 'leave' then
  redis.call('DEL', KEYS[1]); return cjson.encode({ok=true})
end
return cjson.encode({error=400})
"""


def description(value, kind):
    if not isinstance(value, dict) or value.get('type') != kind or not isinstance(value.get('sdp'), str) or not 1 <= len(value['sdp']) <= 40000:
        raise RoomError(400, '연결 정보가 올바르지 않아요.')
    return {'type': kind, 'sdp': value['sdp']}


def handle(data, client_ip):
    if not isinstance(data, dict):
        raise RoomError(400, '잘못된 요청입니다.')
    action, token = data.get('action'), data.get('token', '')
    if action not in ('create', 'join', 'poll', 'answer', 'leave') or not isinstance(token, str) or not re.fullmatch(r'[a-f0-9]{64}', token):
        raise RoomError(400, '잘못된 요청입니다.')
    # Keep guessing/creation bounded; normal room polling has a separate budget.
    bucket = 'poll' if action == 'poll' else 'write'
    key = 'uphill:limit:' + hashlib.sha256(client_ip.encode()).hexdigest()[:24] + ':' + bucket
    count = redis('EVAL', "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],60) end; return n", 1, key)
    if int(count) > (600 if bucket == 'poll' else 60):
        raise RoomError(429, '요청이 많아요. 잠시 후 다시 시도해주세요.')
    if action == 'create':
        offer = description(data.get('offer'), 'offer')
        for _ in range(10):
            code = str(secrets.randbelow(900000) + 100000)
            room = json.dumps({'owner': token, 'offer': offer})
            if redis('SET', 'uphill:room:' + code, room, 'EX', TTL, 'NX'):
                return {'code': code, 'expiresIn': TTL}
        raise RoomError(503, '방을 만들지 못했어요. 다시 시도해주세요.')
    code = data.get('code', '')
    if not isinstance(code, str) or not re.fullmatch(r'[0-9]{6}', code):
        raise RoomError(400, '6자리 방번호를 입력해주세요.')
    answer = description(data.get('answer'), 'answer') if action == 'answer' else None
    result = json.loads(redis('EVAL', ROOM_SCRIPT, 1, 'uphill:room:' + code, action, token, json.dumps(answer)))
    if 'error' in result:
        status = result['error']
        raise RoomError(status, {404: '방이 없거나 만료됐어요.', 409: '이미 다른 친구가 입장한 방이에요.', 403: '방 접근 권한이 없어요.'}.get(status, '잘못된 요청입니다.'))
    return result


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 50000:
                raise RoomError(413, '요청 크기가 올바르지 않아요.')
            if self.headers.get_content_type() != 'application/json':
                raise RoomError(415, 'JSON 요청만 지원합니다.')
            # Reject cross-site browser requests; same-origin fetch needs no CORS.
            if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                raise RoomError(403, '같은 사이트에서 접속해주세요.')
            ip = self.headers.get('x-vercel-forwarded-for', self.client_address[0]).split(',')[0]
            result, status = handle(json.loads(self.rfile.read(size)), ip), 200
        except RoomError as exc:
            result, status = {'error': exc.message}, exc.status
        except (ValueError, TypeError):
            result, status = {'error': '잘못된 요청입니다.'}, 400
        except Exception:
            result, status = {'error': '방 서버 연결이 지연됐어요. 다시 시도해주세요.'}, 503
        body = json.dumps(result, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
