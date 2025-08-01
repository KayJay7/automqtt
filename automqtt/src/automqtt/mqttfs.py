# pyright: standard

from abc import abstractmethod
from pathlib_abc import ReadablePath, PathInfo, PathParser
import handlers
from typing import Never, Iterable, Optional, Self
from pathlib import PurePosixPath

__all__ = ["HandlerTree", "MQTTPath"]


type _Handler = handlers.Handler
type _TreeItem = _Handler | dict[str, _TreeItem]
type HandlerTree = dict[str, _TreeItem]


class PosixParser(PathParser):
    sep: str = PurePosixPath.parser.sep
    altsep: Optional[str] = PurePosixPath.parser.altsep
    curdir: str = PurePosixPath.parser.curdir

    def split(self, path: str) -> tuple[str, str]:
        return PurePosixPath.parser.split(path)

    def splitext(self, path: str) -> tuple[str, str]:
        return PurePosixPath.parser.splitext(path)

    def normcase(self, path: str) -> str:
        return PurePosixPath.parser.normcase(path)

    def join(self, a: str, *b: str) -> str:
        return PurePosixPath.parser.join(a, *b)

    def normpath(self, path: str) -> str:
        return PurePosixPath.parser.normpath(path)

    def relpath(self, path: str, start: str) -> str:
        return PurePosixPath.parser.relpath(path, start)


posixparser = PosixParser()


class _MQTTPathInfoABS(PathInfo):
    @property
    @abstractmethod
    def handler(self) -> _Handler: ...

    @property
    @abstractmethod
    def children(self) -> Iterable[str]: ...


class _MQTTPathInfo(_MQTTPathInfoABS):
    _exists: bool
    _is_dir: bool
    _is_file: bool
    _handler: None | _Handler
    _children: None | Iterable[str]
    _parts: list[str]

    def __init__(
        self,
        parts: list[str],
        item: None | _TreeItem = None,
    ):
        self._parts = parts
        if item is None:
            self._exists = False
            self._is_dir = False
            self._is_file = False
            self._handler = None
            self._children = None
        elif isinstance(item, dict):
            self._exists = True
            self._is_dir = True
            self._is_file = False
            self._handler = None
            self._children = item
        else:
            self._exists = True
            self._is_dir = False
            self._is_file = True
            self._handler = item
            self._children = None

    @property
    def handler(self) -> _Handler:
        if self._handler is None:
            if self._is_dir:
                raise IsADirectoryError(self)
            raise FileNotFoundError(self)
        return self._handler

    @property
    def children(self) -> Iterable[str]:
        if self._children is None:
            if self._is_file:
                raise NotADirectoryError(self)
            raise FileNotFoundError(self)
        return self._children

    def exists(self, *, follow_symlinks: bool = True) -> bool:
        return self._exists

    def is_dir(self, *, follow_symlinks: bool = True) -> bool:
        return self._is_dir

    def is_file(self, *, follow_symlinks: bool = True) -> bool:
        return self._is_file

    def is_symlink(self) -> bool:
        return False


class MQTTPath(ReadablePath, _MQTTPathInfoABS):
    _filetree: _TreeItem
    _segments: tuple[str, ...]
    __info: _MQTTPathInfo  # cached
    __hash: int  # cached
    __str: str  # cached
    __self_parts_cached: list[str]  # cached

    def __init__(self, *pathsegments: str, tree: _TreeItem):
        self._segments = pathsegments
        self._filetree = tree

    def __str__(self) -> str:
        try:
            return self.__str
        except AttributeError:
            if len(self._segments) > 0:
                self.__str = self.parser.join(*self._segments)
            else:
                self.__str = ""

        return self.__str

    def __hash__(self) -> int:
        try:
            return self.__hash
        except AttributeError:
            self.__hash = hash(str(self))

        return self.__hash

    def __eq__(self, other: object) -> bool:
        if isinstance(other, MQTTPath):
            if self._filetree is other._filetree:
                if str(self) == str(other):
                    return True

        return False

    @property
    def parser(self) -> PosixParser:
        return posixparser

    @property
    def __self_parts(self) -> Iterable[str]:
        try:
            return self.__self_parts_cached
        except AttributeError:
            self.__self_parts_cached = list(self.__parts(str(self)))

        return self.__self_parts_cached

    @property
    def anchor(self) -> str:
        return next(iter(self.__self_parts))

    @property
    def info(self) -> _MQTTPathInfo:
        try:
            return self.__info
        except AttributeError:
            parts: list[str] = list(self.__parts(self.parser.normpath(str(self))))
            cur: _TreeItem = self._filetree
            for part in parts:
                if part != self.parser.curdir and part != self.parser.sep:
                    if callable(cur) or part not in cur:
                        self.__info = _MQTTPathInfo(parts)
                        return self.__info
                    else:
                        cur = cur[part]
            self.__info = _MQTTPathInfo(parts, cur)

        return self.__info

    def with_segments(self, *pathsegments: str) -> "MQTTPath":
        return MQTTPath(*pathsegments, tree=self._filetree)

    def resolve(self) -> "MQTTPath":
        return self.with_segments(*self.info._parts)

    def __parts(self, path: str) -> Iterable[str]:
        parts = []
        head = path
        while len(head):
            head, tail = self.parser.split(head)
            parts.append(tail)
        return reversed(parts)

    def iterdir(self) -> Iterable[Self]:
        if not callable(self._filetree):
            return ((self / name) for name in self.info.children)
        else:
            return ()

    def readlink(self) -> Never:
        raise NotImplementedError

    def __open_rb__(self, buffering: int = -1) -> Never:
        raise NotImplementedError

    def strip_anchor(self) -> str:
        resolved = self.resolve()
        return self.parser.relpath(str(resolved), resolved.anchor)

    def relative_to(self, other: "str | MQTTPath", *, walk_up=False) -> str:
        resolved = self.resolve()
        if isinstance(other, MQTTPath):
            other = str(other.resolve())
        return self.parser.relpath(str(resolved), other)

    #### PathInfo ####

    @property
    def handler(self) -> _Handler:
        return self.info.handler

    @property
    def children(self) -> Iterable[str]:
        return self.info.children

    def exists(self, *, follow_symlinks: bool = True) -> bool:
        return self.info.exists(follow_symlinks=follow_symlinks)

    def is_dir(self, *, follow_symlinks: bool = True) -> bool:
        return self.info.is_dir(follow_symlinks=follow_symlinks)

    def is_file(self, *, follow_symlinks: bool = True) -> bool:
        return self.info.is_file(follow_symlinks=follow_symlinks)

    def is_symlink(self) -> bool:
        return self.info.is_symlink()
