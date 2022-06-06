from typing import Any, TYPE_CHECKING

from enums import TrackEventType

if TYPE_CHECKING:
    from player import Player


__all__ = (
    'BaseEventPayload',
    'StatsEventPayload',
    'TrackEventPayload'
)


class BaseEventPayload:

    __slots__ = (
        'raw',
        'op'
    )

    def __init__(self, **payload: Any):
        self.raw: dict[str, Any] = payload
        self.op: str = payload['op']


class StatsEventPayload(BaseEventPayload):

    __slots__ = (
        'playing',
        'players',
        'reservable_memory',
        'free_memory',
        'used_memory',
        'allocated_memory',
        'cores',
        'system_load',
        'lavalink_load',
        'uptime'
    )

    def __init__(self, **payload: Any):
        super().__init__(**payload)

        self.playing: int = payload['playingPlayers']
        self.players: int = payload['players']

        memory = payload['memory']
        self.reservable_memory: int = memory['reservable']
        self.free_memory: int = memory['free']
        self.used_memory: int = memory['used']
        self.allocated_memory: int = memory['allocated']

        cpu = payload['cpu']
        self.cores: int = cpu['cores']
        self.system_load: float = cpu['systemLoad']
        self.lavalink_load: float = cpu['lavalinkLoad']

        self.uptime: int = payload['uptime']

    def __repr__(self) -> str:
        return f'<StatsPayload: playing="{self.playing}", connected="{self.players}", uptime="{self.uptime}">'


class TrackEventPayload(BaseEventPayload):

    __slots__ = (
        'player',
        'track',
        'type',
        '_event',
        'reason',
        'error'
    )

    def __init__(self, player: 'Player', **payload: Any):
        super().__init__(**payload)
        self.player: 'Player' = player

        self.reason: str | None = None
        self.error: str | None = None

        match payload['type']:

            case 'TrackEndEvent':
                self.type: TrackEventType = TrackEventType.END
                self.reason: str = payload['reason']
                self._event: str = 'track_end'

            case 'TrackStartEvent':
                self.type: TrackEventType = TrackEventType.START
                self._event = 'track_start'

            case 'TrackExceptionEvent':
                self.type: TrackEventType = TrackEventType.EXCEPTION
                self.error: str = payload['error']
                self._event: str = 'track_exception'

            case 'TrackStuckEvent':
                self.type: TrackEventType = TrackEventType.STUCK
                self._event: str = 'track_stuck'
