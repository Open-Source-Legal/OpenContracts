# Test: WebSocket Auth Handshake (subprotocol + in-band refresh)

## Purpose

Verify that:

1. WebSocket auth carries the JWT only via `Sec-WebSocket-Protocol`, never URL.
2. Token rotation is in-band and does not churn the socket.
3. Old `?token=` transport no longer authenticates (hard cutover).
4. User-pk swap on a live socket is refused.

## Prerequisites

- Local stack running: `docker compose -f local.yml up`.
- A Django superuser with a known password. To create or reset one:

  ```bash
  docker compose -f local.yml exec django python manage.py shell -c "
  from django.contrib.auth import get_user_model
  u = get_user_model().objects.filter(is_superuser=True).first()
  u.set_password('testpass123')
  u.save()
  print(f'Password set for {u.username}')
  "
  ```

## Steps

### 1. Mint a fresh JWT

```bash
TOKEN=$(docker compose -f local.yml exec django python manage.py shell -c "
from graphql_jwt.shortcuts import get_token
from django.contrib.auth import get_user_model
print(get_token(get_user_model().objects.filter(is_superuser=True).first()))
" | tr -d '\r' | tail -1)
echo "$TOKEN"
```

**Expected:** A long JWT string (3 dot-separated segments).

### 2. Regression — query-string token must be ignored

```bash
python3 -c "
import asyncio, websockets
async def main():
    try:
        async with websockets.connect(
            f'ws://localhost:8000/ws/notification-updates/?token=$TOKEN'
        ) as ws:
            msg = await asyncio.wait_for(ws.recv(), 5)
            print('UNEXPECTED frame:', msg)
    except Exception as e:
        print('OK — connection rejected:', type(e).__name__, e)
asyncio.run(main())
"
```

**Expected:** Connection rejected. `NotificationUpdatesConsumer` requires auth and the URL token is not consulted, so the consumer closes 4001 (or the handshake fails because no subprotocol was negotiated).

### 3. Subprotocol-based handshake succeeds

```bash
python3 -c "
import asyncio, json, websockets
async def main():
    async with websockets.connect(
        'ws://localhost:8000/ws/notification-updates/',
        subprotocols=['opencontracts.jwt.v1', '$TOKEN']
    ) as ws:
        msg = json.loads(await asyncio.wait_for(ws.recv(), 5))
        print('Frame 1:', msg)
        msg = json.loads(await asyncio.wait_for(ws.recv(), 5))
        print('Frame 2:', msg)
asyncio.run(main())
"
```

**Expected:**
- Frame 1: `{"type":"AUTH_OK", "user_id":..., "anonymous":false, "refreshed":false, ...}`
- Frame 2: `{"type":"CONNECTED", ...}`

### 4. In-band refresh (no reconnect)

```bash
python3 -c "
import asyncio, json, websockets
async def main():
    async with websockets.connect(
        'ws://localhost:8000/ws/notification-updates/',
        subprotocols=['opencontracts.jwt.v1', '$TOKEN']
    ) as ws:
        await asyncio.wait_for(ws.recv(), 5)  # AUTH_OK
        await asyncio.wait_for(ws.recv(), 5)  # CONNECTED
        await ws.send(json.dumps({'type':'AUTH','token':'$TOKEN'}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), 5))
        print('Refresh result:', msg)
asyncio.run(main())
"
```

**Expected:** `{"type":"AUTH_OK","refreshed":true,...}`. No reconnect occurred.

### 5. User-pk swap is refused

```bash
OTHER_TOKEN=$(docker compose -f local.yml exec django python manage.py shell -c "
from django.contrib.auth import get_user_model
from graphql_jwt.shortcuts import get_token
User = get_user_model()
u, _ = User.objects.get_or_create(username='wsswaptest', defaults={'is_active': True})
print(get_token(u))
" | tr -d '\r' | tail -1)

python3 -c "
import asyncio, json, websockets
async def main():
    try:
        async with websockets.connect(
            'ws://localhost:8000/ws/notification-updates/',
            subprotocols=['opencontracts.jwt.v1', '$TOKEN']
        ) as ws:
            await asyncio.wait_for(ws.recv(), 5)  # AUTH_OK
            await asyncio.wait_for(ws.recv(), 5)  # CONNECTED
            await ws.send(json.dumps({'type':'AUTH','token':'$OTHER_TOKEN'}))
            msg = await asyncio.wait_for(ws.recv(), 5)
            print('Swap response:', msg)
            await asyncio.wait_for(ws.recv(), 5)
    except websockets.ConnectionClosed as e:
        print(f'OK — server closed (code {e.code}, reason: {e.reason!r})')
asyncio.run(main())
"
```

**Expected:** Server emits `{"type":"AUTH_FAILED","reason":"USER_MISMATCH"}` then closes 4002.

### 6. Browser DevTools sanity

1. `cd frontend && yarn start` and log in.
2. Open Chrome DevTools → Network → WS filter.
3. Inspect the `notification-updates/` WebSocket request:
   - **Request URL:** must NOT contain `token=` query parameter.
   - **Request Headers:** must show `Sec-WebSocket-Protocol: opencontracts.jwt.v1, <jwt>`.
   - **Response Headers:** must show `Sec-WebSocket-Protocol: opencontracts.jwt.v1`.
4. In the WS Messages tab, confirm the FIRST frame is `AUTH_OK`.
5. (Optional) trigger an Auth0 silent renewal (or wait for one). Confirm the WS connection is NOT torn down — only a single `{"type":"AUTH","token":"..."}` frame should appear in the message list, followed by `AUTH_OK refreshed:true`.

## Cleanup

None required for steps 1-4. Step 5 creates a `wsswaptest` user; remove it if desired:

```bash
docker compose -f local.yml exec django python manage.py shell -c "
from django.contrib.auth import get_user_model
get_user_model().objects.filter(username='wsswaptest').delete()
"
```
