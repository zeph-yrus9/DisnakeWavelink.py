"""MIT License

Copyright (c) 2019-Present PythonistaGuild

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import asyncio
import logging
import threading
import time
from concurrent.futures import CancelledError
from typing import Any, Optional, TYPE_CHECKING

import aiohttp

from backoff import Backoff
from payload import *

if TYPE_CHECKING:
    from node import Node
    from player import Player


logger = logging.getLogger(__name__)


class KeepAlive(threading.Thread):

    def __init__(self, websocket: 'Websocket'):
        super().__init__()
        self.daemon = True

        self.websocket: 'Websocket' = websocket
        self.loop: asyncio.AbstractEventLoop = websocket.loop
        self.stopped: bool = False

    def run(self) -> None:
        while not self.stopped:
            if not self.websocket.is_connected():
                time.sleep(self.websocket.retry)
                continue

            try:
                message = asyncio.run_coroutine_threadsafe(self.websocket.websocket.receive(), loop=self.loop).result()
            except CancelledError:
                self.stopped = True
            else:
                self._get_payload(message)

    def _get_payload(self, message: aiohttp.WSMessage) -> dict[str, dict[str, Any]] | None:
        print(message)  # TODO: Remove...
        if message.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
            self.loop.call_soon_threadsafe(self.websocket._message_queue.put_nowait, {'op': 'CLOSED'})
            return

        if message.data == 1011:
            logger.error('Lavalink encountered an internal error which can not be resolved. '
                         'Make sure your Lavalink sever is up to date, and try restarting.')

            asyncio.run_coroutine_threadsafe(self.websocket.cleanup(), loop=self.loop)
            return

        if message.data is None:
            logger.info('Received a message from Lavalink with empty data. Disregarding...')
            return

        data = message.json()
        logger.debug(f'Received a message from Lavalink: {data}')

        op = data.get('op', None)
        if not op:
            logger.info('Message "op" was None. Disregarding.')
            return

        self.loop.call_soon_threadsafe(self.websocket._message_queue.put_nowait, data)


class Websocket:

    __slots__ = (
        'node',
        'http',
        'host',
        'ws_host',
        'heartbeat',
        'websocket',
        'backoff',
        'retry',
        'attempts',
        '_original_attempts',
        'resume_key',
        '_message_queue',
        'loop',
        'keep_alive',
        '_keep_alive_closed'
    )

    def __init__(
            self,
            *,
            node: 'Node',
            host: str,
            port: int,
            heartbeat: float = 30.0,
            http: bool = False,
            secure: bool = False,
            attempts: int | None = None,
            resume_key: str
    ):
        self.node: 'Node' = node

        self.http: bool = http

        self.host: str = f'{"https://" if secure else "http://"}{host}:{port}'
        self.ws_host: str = f'{"wss://" if secure else "ws://"}{host}:{port}'
        self.heartbeat: float = heartbeat

        self.websocket: aiohttp.ClientWebSocketResponse = None  # type: ignore
        self.backoff: Backoff = Backoff()

        self.retry: float = 1
        self.attempts: int | None = attempts
        self._original_attempts: int | None = attempts
        self.resume_key: str = resume_key

        self._message_queue: asyncio.Queue = asyncio.Queue()

        self.loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        self.keep_alive: 'KeepAlive' = KeepAlive(self)
        self.keep_alive.start()

        self._keep_alive_closed: bool = False

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": self.node._password,
            "User-Id": str(self.node.client.user.id),
            "Client-Name": "WaveLink 2.0",
            'Resume-Key': self.resume_key
        }

    def is_connected(self) -> bool:
        return self.websocket is not None and not self.websocket.closed

    async def connect(self) -> None:
        if self.is_connected():
            raise RuntimeError(f'The Wavelink websocket for node "{self.node}" is already connected.')

        async with aiohttp.ClientSession() as session:
            url = self.host if self.http else self.ws_host

            try:
                self.websocket = await session.ws_connect(url=url, heartbeat=self.heartbeat, headers=self.headers)
            except Exception as e:
                if isinstance(e, aiohttp.WSServerHandshakeError) and e.status == 401:
                    logger.error(f'Authorization failed for node: "{self.node}". '
                                 f'Please check your password and try again.')
                else:
                    logger.error(f'An error occurred connecting to node: "{self.node}". {e}')

            session.detach()

        if self.is_connected():
            self.attempts = self._original_attempts
            self.dispatch('node_ready', self.node)
        else:
            await self._reconnect()
            return

        asyncio.create_task(self._listen())

    async def _reconnect(self) -> None:
        self.retry = self.backoff.calculate()

        if self.attempts == 0:
            logger.error('Wavelink 2.0 was unable to connect, and has exhausted the reconnection attempt limit. '
                         'Please check your Lavalink Node is started and your connection details are correct.')

            await self.cleanup()
            return

        attempts = f'{self.attempts} attempt(s) remaining.' if self.attempts else ''
        logger.error(f'Wavelink 2.0 was unable to connect, retrying connection in: "{self.retry}" seconds. {attempts}')

        if self.attempts:
            self.attempts -= 1

        await asyncio.sleep(self.retry)
        await self.connect()

    async def _listen(self) -> None:
        while True:
            payload = await self._message_queue.get()

            match payload['op']:

                case 'CLOSED':
                    await self._reconnect()
                    return

                case 'stats':
                    payload = StatsEventPayload(**payload)

                    self.dispatch('stats_update', payload)

                case 'event':
                    player = self.get_player(payload)
                    if player is None:
                        logger.warning('Received payload from Lavalink without an attached player. Disregarding.')
                        continue

                    # TODO: Source to None...

                    payload = TrackEventPayload(player, **payload)
                    self.dispatch(payload, event=payload._event)

                case 'playerUpdate':
                    ...

                case _:
                    logger.info(f'Received unknown payload from Lavalink: <{payload}>. '
                                f'If this continues consider making a ticket on the Wavelink GitHub. '
                                f'https://github.com/PythonistaGuild/Wavelink')

    def get_player(self, payload) -> Optional['Player']:
        try:
            player = self.node.get_player(int(payload['guildId']))
        except KeyError:
            return None

        return player

    def dispatch(self, event, *args: Any, **kwargs: Any) -> None:
        self.node.client.dispatch(f"wavelink_{event}", *args, **kwargs)

    async def send(self, **data: Any) -> None:
        if not self.is_connected():
            logger.warning('Trying to send payload to Lavalink while websocket is disconnected. Disregarding.')
            return

        data = self.node.dumps(data)
        if isinstance(data, bytes):
            # Some JSON libraries serialize to bytes
            # Yet Lavalink does not support binary websockets
            # So we need to decode. In the future, maybe
            # self._websocket.send_bytes could be used
            # if Lavalink ever implements it
            data = data.decode("utf-8")

        await self.websocket.send_str(data)

    async def cleanup(self) -> None:
        self.keep_alive.stopped = True

        try:
            await self.websocket.close()
        except AttributeError:
            pass
