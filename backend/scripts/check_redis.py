import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from app.config import settings
import redis

r = redis.from_url(settings.redis_url)
print("Redis ping:", r.ping())
keys = r.keys('dramatiq:*')
print("Dramatiq keys:", keys)
for k in keys:
    t = r.type(k)
    length = r.llen(k) if t == b'list' else 'n/a'
    print(f"  {k.decode()}: type={t.decode()}, len={length}")
