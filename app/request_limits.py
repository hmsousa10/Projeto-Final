"""Limite de corpo antes da desserialização JSON, incluindo transferência por chunks."""
from starlette.responses import JSONResponse
import asyncio


class BodyLimitMiddleware:
    def __init__(self, app, max_bytes=65536, timeout_seconds=10):
        self.app = app
        self.max_bytes = max_bytes
        self.timeout_seconds = timeout_seconds

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        length = headers.get(b'content-length')
        if length is not None:
            try:
                size = int(length)
                if size < 0:
                    raise ValueError
            except ValueError:
                return await JSONResponse({'detail': 'Tamanho de pedido inválido.'}, 400)(scope, receive, send)
            if size > self.max_bytes:
                return await JSONResponse({'detail': 'O pedido excede o limite de 64 KiB.'}, 413)(scope, receive, send)
        chunks = []
        total = 0
        deadline=asyncio.get_running_loop().time()+self.timeout_seconds
        while True:
            try:
                async with asyncio.timeout_at(deadline):
                    message = await receive()
            except TimeoutError:
                return await JSONResponse({'detail':'Tempo de leitura do pedido excedido.'},408,
                    headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})(scope,receive,send)
            if message['type'] == 'http.disconnect':
                return
            chunk = message.get('body', b'')
            total += len(chunk)
            if total > self.max_bytes:
                return await JSONResponse({'detail': 'O pedido excede o limite de 64 KiB.'}, 413)(scope, receive, send)
            chunks.append(chunk)
            if not message.get('more_body', False):
                break
        body = b''.join(chunks)
        delivered = False

        async def replay():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {'type': 'http.request', 'body': body, 'more_body': False}

        await self.app(scope, replay, send)
