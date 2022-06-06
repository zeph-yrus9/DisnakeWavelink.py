import enum


class TrackEventType(enum.Enum):

    END = enum.auto()
    START = enum.auto()
    EXCEPTION = enum.auto()
    STUCK = enum.auto()
