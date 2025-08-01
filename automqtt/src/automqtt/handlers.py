# pyright: standard

from enum import Enum
from itertools import groupby
import json
import paho.mqtt.client as mqtt
from typing import Callable, ClassVar
from devices import *
import mqttfs

__all__ = [
    "Handler",
    "PowerStatusBehaviour",
    "TimerStatusBehaviour",
    "time_marshalled",
    "time_unmarshalled",
    "retain",
]


def all_equal(iterable):
    g = groupby(iterable)
    return next(g, True) and not next(g, False)


type _MQTTPath = mqttfs.MQTTPath

type Handler = Callable[[mqtt.Client, _MQTTPath, mqtt.MQTTMessage], None]

type _StateHandler[T] = Callable[[T, mqtt.Client, _MQTTPath, mqtt.MQTTMessage], T]


class _StatefulHandler[T]:
    _storage: T
    _handler: _StateHandler

    def __init__(self, initial_storage: T, handler: _StateHandler) -> None:
        self._storage = initial_storage

    def __call__(
        self, client: mqtt.Client, fs: _MQTTPath, msg: mqtt.MQTTMessage
    ) -> None:
        self._storage = self._handler(self._storage, client, fs, msg)


class _Kind(Enum):
    FILE = 1
    DIR = 2
    MISSING = 3


class _FsCache:

    _kind_cache: ClassVar[dict[_MQTTPath, _Kind]] = {}

    @classmethod
    def _cache(cls, path: _MQTTPath) -> _Kind:
        try:
            return cls._kind_cache[path]
        except KeyError:
            # print("cache miss")
            if not path.exists():
                cls._kind_cache[path] = _Kind.MISSING
                return _Kind.MISSING
            if path.is_dir():
                cls._kind_cache[path] = _Kind.DIR
                return _Kind.DIR
            cls._kind_cache[path] = _Kind.FILE
            return _Kind.FILE

    @classmethod
    def check_dir(cls, path: _MQTTPath) -> bool:
        # return path.is_dir()
        return cls._cache(path) == _Kind.DIR

    @classmethod
    def check_file(cls, path: _MQTTPath) -> bool:
        # return path.is_file()
        return cls._cache(path) == _Kind.FILE

    @classmethod
    def check_exists(cls, path: _MQTTPath) -> bool:
        # return path.exists()
        return not cls._cache(path) == _Kind.MISSING


# Time marshaling from dumb slider to tasmota
def time_marshalled(client: mqtt.Client, fs: _MQTTPath, msg: mqtt.MQTTMessage):
    try:
        target_time = int(msg.payload)
        true_time = (target_time - 1) % 24

        topic = fs / "cmnd" / (fs / msg.topic).strip_anchor()

        if _FsCache.check_dir(topic):
            client.publish(
                str(topic.resolve()),
                f'{{"Time" : "{true_time}:59"}}',
                qos=1,
            )
        else:
            if not _FsCache.check_exists(topic):
                raise FileNotFoundError(topic)
            raise NotADirectoryError(topic)
    except ValueError:
        print(f'Error setting time, "{msg.payload}"')


# Time unmarshaling from tasmota to dumb slider
def time_unmarshalled(timer_index: int, topic: Topics) -> Handler:
    timer_name = f"Timer{timer_index}"
    topic_path = f"stat/{topic.value}/TIMER{timer_index}/unmarshalled"

    def unmarshal(client: mqtt.Client, fs: _MQTTPath, msg: mqtt.MQTTMessage):
        try:
            payload = json.loads(msg.payload)
            split_time = payload[timer_name]["Time"].split(":")
            hours = int(split_time[0])
            if int(split_time[1]) >= 30:
                hours += 1
                hours %= 24

            topic = fs / topic_path
            if _FsCache.check_dir(topic):
                client.publish(
                    topic_path,
                    str(hours),
                    retain=True,
                    qos=1,
                )
            else:
                if not _FsCache.check_exists(topic):
                    raise FileNotFoundError(topic)
                raise NotADirectoryError(topic)
        except KeyError:
            print(f'Info, cannot unmarshal time, missing key in object "{msg.payload}"')
        except json.JSONDecodeError:
            print(f'Error unmarshalling time, cannot decode "{msg.payload}"')
        except ValueError:
            print(f'Error unmarshalling time, cannot decode "{msg.payload}"')

    return unmarshal


# Make messages retained in a subtopic
def retain(client: mqtt.Client, fs: _MQTTPath, msg: mqtt.MQTTMessage):
    topic_path = msg.topic + "/retained"
    topic = fs / topic_path
    if _FsCache.check_dir(topic):
        client.publish(topic_path, msg.payload, retain=True, qos=1)
    else:
        if not _FsCache.check_exists(topic):
            raise FileNotFoundError(topic)
        raise NotADirectoryError(topic)


# Print information on the message
def debug(_c: mqtt.Client, _u: _MQTTPath, msg: mqtt.MQTTMessage):
    print(f'{msg.topic}: "{msg.payload}"')


# No operation
def noop(_c: mqtt.Client, _u: _MQTTPath, msg: mqtt.MQTTMessage):
    pass


# Class that handles combined power of N devices
class PowerStatusBehaviour[T: Enum]:
    _power_state: dict[T, bool]
    _topic: str

    def __init__(self, topic: Topics, enum: type[T]):
        self._power_state = {}
        for device in enum:
            self._power_state[device] = False

        self._topic = f"stat/{topic.value}/POWER"

    def handle_power(
        self, client: mqtt.Client, fs: _MQTTPath, device: T, status: bytes
    ):
        self._power_state[device] = status == b"ON"
        topic = fs / self._topic
        if _FsCache.check_dir(topic):
            if all(self._power_state.values()):
                client.publish(self._topic, "ON", retain=True, qos=1)
            else:
                client.publish(self._topic, "OFF", retain=True, qos=1)
        else:
            if not _FsCache.check_exists(topic):
                raise FileNotFoundError(topic)
            raise NotADirectoryError(topic)

    def get_handler(self, device: T) -> Handler:
        return lambda client, fs, msg: self.handle_power(
            client, fs, device, msg.payload
        )


class TimerStatusBehaviour[T: Enum]:
    _timer_state: dict[T, int]
    topic: str

    def __init__(self, topic: Topics, timer_index: int, enum: type[T]):
        self._timer_state = {}
        different_value = 0
        for device in enum:
            self._timer_state[device] = different_value
            different_value += 1
            different_value %= 24

        self._topic = f"stat/{topic.value}/TIMER{timer_index}/unmarshalled"

    def handle_timer(
        self, client: mqtt.Client, fs: _MQTTPath, device: T, status: bytes
    ):
        hours = int(status)
        self._timer_state[device] = hours
        topic = fs / self._topic
        if _FsCache.check_dir(topic):
            if all_equal(self._timer_state.values()):
                client.publish(self._topic, str(hours), retain=True, qos=1)
            else:
                client.publish(self._topic, "-", retain=True, qos=1)
        else:
            if not _FsCache.check_exists(topic):
                raise FileNotFoundError(topic)
            raise NotADirectoryError(topic)

    def get_handler(self, device: T) -> Handler:
        return lambda client, fs, msg: self.handle_timer(
            client, fs, device, msg.payload
        )
