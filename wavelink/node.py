import copy
import json
import uuid
from typing import Any, Callable, Optional, TYPE_CHECKING

from discord.ext import commands
from discord import Client

from utilities import classproperty
from websocket import Websocket

if TYPE_CHECKING:
    from player import Player


class Node:
    """The Wavelink Node Object.

    Attributes
    ----------
    client:
    Union[:class:`discord.Client`, :class:`discord.ext.commands.Bot`, :class:`discord.ext.commands.AutoShardedBot]
        The discord Client associated with this Node.
    host: str
        The host address or IP used to connect this Node.
    port: int
        The port to used to connect this Node.
    heartbeat: float
        The connection heartbeat as a float in seconds.
    http: bool
        Whether the connection is using a http address in place of a websocket address.
    secure: bool
        Whether the connection is using https or wss. (Secure connections).
    reconnection_attempts: int
        The amount of times this Node will attempt to reconnect in case of a disconnection.
    resume_key: str
        The resume key sent to Lavalink for resuming sessions after reconnects.
    dumps: Callable[[Any], str]
        The JSON dumps method for converting JSON into a string or bytes for Lavalink.
        Defaults to the builtin json.dumps method.
    identifier: str
        The Nodes' unique identifier string.

    .. warning::

        This class should not be instantiated manually. Please use the connect method of :class:`NodePool` instead.
    """

    __slots__ = (
        'client',
        'host',
        'port',
        '_password',
        'heartbeat',
        'http',
        'secure',
        'reconnection_attempts',
        'resume_key',
        'dumps',
        'identifier',
        '_websocket',
        '_players',
    )

    def __init__(self, **attrs):
        self.client: Client | commands.Bot | commands.AutoShardedBot = attrs['client']
        self.host: str = attrs['host']
        self.port: int = attrs['port']
        self._password: str = attrs['password']
        self.heartbeat: float = attrs['heartbeat']
        self.http: bool = attrs['http']
        self.secure: bool = attrs['secure']
        self.reconnection_attempts: int | None = attrs.get('reconnection_attempts', None)
        self.resume_key: str = attrs.get('resume_key', None) or str(uuid.uuid4())
        self.dumps: Callable[[Any], str]
        self.identifier: str = attrs['identifier']

        self._websocket: 'Websocket' = None  # type: ignore

        self._players: dict[int, 'Player'] = {}

    def __repr__(self) -> str:
        return f'<Node: host="{self.host}", port={self.port}, identifier="{self.identifier}">'

    async def _connect(self) -> None:
        websocket = Websocket(
            node=self,
            host=self.host,
            port=self.port,
            heartbeat=self.heartbeat,
            http=self.http,
            secure=self.secure,
            attempts=self.reconnection_attempts,
            resume_key=self.resume_key,
        )

        await websocket.connect()
        self._websocket = websocket

    @property
    def is_connected(self) -> bool:
        """Returns a bool indicating whether the Node is currently connected to Lavalink or not."""
        return self._websocket.is_connected()

    @property
    def players(self) -> dict[int, 'Player']:
        """Returns a Mapping of Guild ID to Player.

        Could be an Empty Mapping if no players are currently active.

        Returns
        -------
        dict[int, :class:'Player']
            A mapping of Guild ID to assigned :class:`Player`.
        """
        return copy.copy(self._players)

    def get_player(self, guild_id: int, /) -> Optional['Player']:
        """Returns a :class:`Player` for the given Guild ID.

        Parameters
        ----------
        guild_id: int
            The Guild ID to fetch the player for.

        Returns
        -------
        Optional[:class:`Player`]
            The :class:`Player` associated with the given Guild ID. Could be `None` if the Guild does not have an
            active player.
        """
        return self._players.get(guild_id, None)


class NodePoolMeta(type):

    _client: Client | commands.Bot | commands.AutoShardedBot

    def __call__(cls, client: Client | commands.Bot | commands.AutoShardedBot):
        cls._client = client

        return super().__call__()


# noinspection PyMethodParameters
class NodePool(metaclass=NodePoolMeta):

    _nodes: dict[str, Node] = {}
    _client: Client | commands.Bot | commands.AutoShardedBot

    async def __aenter__(self) -> 'NodePool':
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        pass

    @classmethod
    async def connect(
            cls,
            *,
            client: Client | commands.Bot | commands.AutoShardedBot | None = None,
            host: str,
            port: int,
            password: str,
            heartbeat: float = 30.0,
            http: bool = False,
            secure: bool = False,
            reconnection_attempts: int | None = None,
            resume_key: str | None = None,
            dumps: Callable[[Any], str] = json.dumps,
            identifier: str | None = None
    ) -> Node:
        """Add and connect a Node to the NodePool.

        Calling this method will attempt to connect to a Lavalink Node with the given parameters.
        All successfully added Nodes can be retrieved via the `nodes` property.

        Parameters
        ----------
        client:
        Union[:class:`discord.Client`, :class:`discord.ext.commands.Bot`, :class:`discord.ext.commands.AutoShardedBot]
            Your Discord Client/Bot used to connect to Lavalink. This parameter is Optional only if client is passed to
            the NodePool when using the NodePool context manager.
        host: str
            The host address or IP to connect to.
        port: int
            The port to connect to.
        password: str
            The password associated with the Lavalink Node.
        heartbeat: float
            The connection heartbeat as a float in seconds.
        http: bool
            Whether the connection should use a http address in place of a websocket address.
        secure: bool
            Whether the connection should use https or wss. (Secure connections).
             Not suitable for localhost connections.
        reconnection_attempts: int
            The amount of times this Node should reattempt to connect in case of a disconnection.
        resume_key: str
            The resume key sent to Lavalink for resuming sessions after reconnects.
        dumps: Callable[[Any], str]
            The JSON dumps method for converting JSON into a string or bytes for Lavalink.
            Defaults to the builtin json.dumps method.
        identifier: str
            The Nodes' identifier string. This should be unique to each Node.

        Returns
        -------
        :class:`Node`
            The connected and available :class:`Node`.

        Raises
        ------
        RuntimeError
            The client parameter was not provided, or used with the NodePool Context Manager.
        ValueError
            The identifier provided was not unique and already exists.

        .. warning::

            This should only be called once for each connected Node, unless manually removing a Node and then re-adding.
            If a Node disconnects, it will automatically try to reconnect with an Exponential Backoff.
        """
        client = client or cls._client

        if client is None:
            raise RuntimeError('The "client" parameter can not be None. Please provide a discord.Client or subclass, '
                               'to this call or the NodePool async context manager.')

        if identifier is None:
            identifier = str(uuid.uuid4())

        if identifier in cls._nodes:
            raise ValueError(f'A node with identifier: "{identifier}" already exists. '
                             f'Please use a different identifier.')

        node = Node(
            client=client,
            host=host,
            port=port,
            password=password,
            heartbeat=heartbeat,
            http=http,
            secure=secure,
            reconnection_attempts=reconnection_attempts,
            resume_key=resume_key,
            dumps=dumps,
            identifier=identifier,
        )

        await node._connect()

        cls._nodes[identifier] = node
        return node

    @classproperty
    def nodes(cls) -> dict[str, Node]:
        """Property which returns a mapping of Node Identifier and corresponding Node Object.

        Could be an Empty Mapping if no Node(s) have been added.

        Returns
        -------
        dict[str, :class:`Node`]
            A mapping of identifier to :class:`Node` object, regardless of their current connection state.
        """
        return copy.copy(cls._nodes)

    @classproperty
    def connected_nodes(cls) -> dict[str, Node]:
        """Property which returns a mapping of Node Identifier and corresponding Node Object, if the Node is connected.

        Could be an Empty Mapping if no Node(s) have been added and/or connected.

        Returns
        -------
        dict[str, :class:`Node`]
            A mapping of identifier to :class:`Node` object, connected Nodes only.
        """
        connected = {}

        for identifier, node in cls._nodes.items():
            if node.is_connected:
                connected[identifier] = node

        return connected

    @classproperty
    def disconnected_nodes(cls) -> dict[str, Node]:
        """Property which returns a mapping of Node Identifier and corresponding Node Object,
         if the Node is disconnected.

        Could be an Empty Mapping if no Node(s) have been added and/or connected previously,
        or if no :class:`Node` is currently disconnected.

        Returns
        -------
        dict[str, :class:`Node`]
            A mapping of identifier to :class:`Node` object, disconnected Nodes only.
        """
        disconnected = {}

        for identifier, node in cls._nodes.items():
            if not node.is_connected:
                disconnected[identifier] = node

        return disconnected

    @classmethod
    def get_node(cls, identifier: str | None = None, /) -> Node:
        """Retrieve a Node from the NodePool with the given identifier. If no identifier is provided,
        the NodePool will return the first Node stored.

        Returns
        -------
        :class:`Node`
            The Node matching the provided identifier or first stored if no identifier was provided.

        Raises
        ------
        RuntimeError
            The NodePool has zero connected Nodes.
        KeyError
            The provided identifier is not associated with any Node.
        """
        if not cls._nodes:
            raise RuntimeError('The NodePool has zero connected Nodes. Connect a Node to continue.')

        if identifier:
            try:
                node = cls._nodes[identifier]
            except KeyError:
                raise KeyError(f'A node with identifier "{identifier}" does not exist.')

            return node
        return list(cls._nodes.values())[0]
