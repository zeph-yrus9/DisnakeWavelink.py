from typing import Any, Optional, TYPE_CHECKING

import discord
from discord.app_commands import Transformer

from node import Node, NodePool

if TYPE_CHECKING:
    from player import Player


class BaseTrack:

    def __init__(self, **payload: Any):
        self.title: str = payload['title']
        self.identifier: Optional[str] = payload.get('identifier')
        self.uri: Optional[str] = payload.get('uri')
        self.author: Optional[str] = payload.get('author')

        self._stream: bool = info.get("isStream", False)  # type: ignore

    @property
    def is_stream(self) -> bool:
        """Property which returns a bool indicating whether this track is a stream."""
        return self._stream


class YouTubeTrack(BaseTrack):

    ST: str = 'ytsearch'


class YouTubeTrackTransformer(Transformer):

    @classmethod
    async def transform(cls, interaction: discord.Interaction, value: Any) -> list[YouTubeTrack]:
        vc: Player = interaction.guild.voice_client  # type: ignore

        node: Node = vc.node or NodePool.get_node()
        tracks: list[YouTubeTrack] = await node.get_tracks(YouTubeTrack, f'ytsearch:{value}')

        return tracks





