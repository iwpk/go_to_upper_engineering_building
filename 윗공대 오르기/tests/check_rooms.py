"""Run the production Lua script, including concurrent guest claims, in fake Redis."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / '.qa/testdeps')]
import fakeredis
from api import rooms


class RoomsTest(unittest.TestCase):
    def setUp(self):
        self.store = fakeredis.FakeRedis(decode_responses=True)
        self.mock = patch.object(rooms, 'redis', self.store.execute_command)
        self.mock.start()
        self.addCleanup(self.mock.stop)
        self.owner, self.guest = 'a' * 64, 'b' * 64
        self.code = self.call('create', offer={'type': 'offer', 'sdp': 'test-offer'})['code']

    def call(self, action, token=None, **data):
        return rooms.handle(dict(action=action, token=token or self.owner,
                                 code=getattr(self, 'code', ''), **data), '127.0.0.1')

    def test_exchange_and_auth(self):
        self.assertRegex(self.code, r'^[0-9]{6}$')
        self.assertEqual(self.call('join', self.guest)['offer']['sdp'], 'test-offer')
        self.assertTrue(self.call('poll')['joined'])
        answer = {'type': 'answer', 'sdp': 'test-answer'}
        self.call('answer', self.guest, answer=answer)
        self.assertEqual(self.call('poll')['answer'], answer)
        with self.assertRaises(rooms.RoomError) as err:
            self.call('leave', 'c' * 64)
        self.assertEqual(err.exception.status, 403)
        self.call('leave')
        with self.assertRaises(rooms.RoomError) as err:
            self.call('poll')
        self.assertEqual(err.exception.status, 404)

    def test_atomic_join_and_retry(self):
        def join(i):
            try:
                self.call('join', f'{i:064x}')
                return i
            except rooms.RoomError as err:
                self.assertEqual(err.status, 409)
        with ThreadPoolExecutor(max_workers=8) as pool:
            winners = [i for i in pool.map(join, range(1, 9)) if i is not None]
        self.assertEqual(len(winners), 1)
        self.call('join', f'{winners[0]:064x}')  # Idempotent retry.

    def test_expiry_preserved_and_missing(self):
        key = 'uphill:room:' + self.code
        self.store.expire(key, 10)
        self.call('join', self.guest)
        self.assertLessEqual(self.store.ttl(key), 10)
        self.store.expire(key, 0)
        time.sleep(0.01)
        self.assertFalse(self.store.exists(key))
        with self.assertRaises(rooms.RoomError) as err:
            self.call('join', self.guest)
        self.assertEqual(err.exception.status, 404)

    def test_validation_and_rate_limit(self):
        with self.assertRaises(rooms.RoomError):
            self.call('answer', self.guest, answer={'type': 'offer', 'sdp': 'bad'})
        with self.assertRaises(rooms.RoomError):
            self.call('poll', 'bad-token')
        for _ in range(58):
            self.call('join', self.guest)
        with self.assertRaises(rooms.RoomError) as err:
            self.call('join', self.guest)
        self.assertEqual(err.exception.status, 429)

    def test_collision_does_not_overwrite(self):
        with patch.object(rooms.secrets, 'randbelow', return_value=int(self.code) - 100000):
            with self.assertRaises(rooms.RoomError) as err:
                self.call('create', offer={'type': 'offer', 'sdp': 'replacement'})
        self.assertEqual(err.exception.status, 503)
        self.assertEqual(self.call('join', self.guest)['offer']['sdp'], 'test-offer')


if __name__ == '__main__':
    unittest.main()
