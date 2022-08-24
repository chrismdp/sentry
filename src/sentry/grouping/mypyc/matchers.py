from typing import TYPE_CHECKING, Any, ClassVar, MutableMapping, Sequence, Tuple, Type

from sentry.grouping.mypyc.exceptions import InvalidEnhancerConfig
from sentry.grouping.utils import get_rule_bool
from sentry.utils.safe import get_path

from .glob import glob_match, translate
from .utils import ExceptionData, MatchFrame, MatchingCache, cached

if TYPE_CHECKING:
    import re

MATCH_KEYS = {
    "path": "p",
    "function": "f",
    "module": "m",
    "family": "F",
    "package": "P",
    "app": "a",
    "type": "t",
    "value": "v",
    "mechanism": "M",
    "category": "c",
}
SHORT_MATCH_KEYS = {v: k for k, v in MATCH_KEYS.items()}

assert len(SHORT_MATCH_KEYS) == len(MATCH_KEYS)  # assert short key names are not reused

FAMILIES = {"native": "N", "javascript": "J", "all": "a"}
REVERSE_FAMILIES = {v: k for k, v in FAMILIES.items()}


MATCHERS = {
    # discover field names
    "stack.module": "module",
    "stack.abs_path": "path",
    "stack.package": "package",
    "stack.function": "function",
    "error.type": "type",
    "error.value": "value",
    "error.mechanism": "mechanism",
    # fingerprinting shortened fields
    "module": "module",
    "path": "path",
    "package": "package",
    "function": "function",
    "category": "category",
    # fingerprinting specific fields
    "family": "family",
    "app": "app",
}


class Match:
    @property
    def description(self) -> str:
        raise NotImplementedError()

    def matches_frame(
        self,
        frames: Sequence[MatchFrame],
        idx: int,
        platform: str,
        exception_data: ExceptionData,
        cache: MatchingCache,
    ) -> bool:
        raise NotImplementedError()

    def _to_config_structure(self, version: int) -> str:
        raise NotImplementedError()

    @staticmethod
    def _from_config_structure(obj: str, version: int) -> "Match":
        val = obj
        if val.startswith("|[") and val.endswith("]"):
            return CalleeMatch(Match._from_config_structure(val[2:-1], version))
        if val.startswith("[") and val.endswith("]|"):
            return CallerMatch(Match._from_config_structure(val[1:-2], version))

        if val.startswith("!"):
            negated = True
            val = val[1:]
        else:
            negated = False
        key = SHORT_MATCH_KEYS[val[0]]
        if key == "family":
            arg = ",".join(_f for _f in [REVERSE_FAMILIES.get(x) for x in val[1:]] if _f)
        else:
            arg = val[1:]

        return FrameMatch.from_key(key, arg, negated)


InstanceKey = Tuple[str, str, bool]


class FrameMatch(Match):

    # Global registry of matchers
    instances: ClassVar[MutableMapping[InstanceKey, "FrameMatch"]] = {}

    @classmethod
    def from_key(cls, key: str, pattern: str, negated: bool) -> "FrameMatch":
        instance_key = (key, pattern, negated)
        if instance_key in cls.instances:
            instance = cls.instances[instance_key]
        else:
            instance = cls.instances[instance_key] = cls._from_key(key, pattern, negated)

        return instance

    @classmethod
    def _from_key(cls, key: str, pattern: str, negated: bool) -> "FrameMatch":
        subclass: Type["FrameMatch"] = {
            "package": PackageMatch,
            "path": PathMatch,
            "family": FamilyMatch,
            "app": InAppMatch,
            "function": FunctionMatch,
            "module": ModuleMatch,
            "category": CategoryMatch,
            "type": ExceptionTypeMatch,
            "value": ExceptionValueMatch,
            "mechanism": ExceptionMechanismMatch,
        }[MATCHERS[key]]

        return subclass(key, pattern, negated)

    def __init__(self, key: str, pattern: str, negated: bool = False, doublestar: bool = False):
        super().__init__()
        try:
            self.key = MATCHERS[key]
        except KeyError:
            raise InvalidEnhancerConfig("Unknown matcher '%s'" % key)
        self.pattern = pattern
        self._compiled_pattern = translate(pattern, doublestar=doublestar)
        self.negated = negated

    @property
    def description(self) -> str:
        return "{}:{}".format(
            self.key,
            self.pattern.split() != [self.pattern] and '"%s"' % self.pattern or self.pattern,
        )

    def matches_frame(
        self,
        frames: Sequence[MatchFrame],
        idx: int,
        platform: str,
        exception_data: ExceptionData,
        cache: MatchingCache,
    ) -> bool:
        match_frame = frames[idx]
        rv = self._positive_frame_match(match_frame, platform, exception_data, cache)
        if self.negated:
            rv = not rv
        return rv

    def _positive_frame_match(
        self,
        match_frame: MatchFrame,
        platform: str,
        exception_data: ExceptionData,
        cache: MatchingCache,
    ) -> bool:
        # Implement is subclasses
        raise NotImplementedError

    def _to_config_structure(self, version: int) -> str:
        if self.key == "family":
            arg = "".join(_f for _f in [FAMILIES.get(x) for x in self.pattern.split(",")] if _f)
        elif self.key == "app":
            arg = {True: "1", False: "0"}.get(get_rule_bool(self.pattern) or False, "")
        else:
            arg = self.pattern
        return ("!" if self.negated else "") + MATCH_KEYS[self.key] + arg


def path_like_match(pattern: "re.Pattern[str]", value: str) -> bool:
    """Stand-alone function for use with ``cached``"""
    if glob_match(value, pattern, ignorecase=False, path_normalize=True):
        return True
    if not value.startswith("/") and glob_match(
        "/" + value, pattern, ignorecase=False, path_normalize=True
    ):
        return True

    return False


class PathLikeMatch(FrameMatch):
    def __init__(self, key: str, pattern: str, negated: bool = False):
        super().__init__(key, pattern.lower(), negated, doublestar=True)

    @staticmethod
    def get_value(frame: MatchFrame) -> Any:
        raise NotImplementedError()

    def _positive_frame_match(
        self,
        match_frame: MatchFrame,
        platform: str,
        exception_data: ExceptionData,
        cache: MatchingCache,
    ) -> bool:
        value = self.get_value(match_frame)
        if value is None:
            return False

        return cached(cache, path_like_match, self._compiled_pattern, value)


class PackageMatch(PathLikeMatch):
    @staticmethod
    def get_value(frame: MatchFrame) -> Any:
        return frame.package


class PathMatch(PathLikeMatch):
    @staticmethod
    def get_value(frame: MatchFrame) -> Any:
        return frame.path


class FamilyMatch(FrameMatch):
    def __init__(self, key: str, pattern: str, negated: bool = False):
        super().__init__(key, pattern, negated)
        self._flags = set(self.pattern.split(","))

    def _positive_frame_match(
        self,
        match_frame: MatchFrame,
        platform: str,
        exception_data: ExceptionData,
        cache: MatchingCache,
    ) -> bool:
        if "all" in self._flags:
            return True

        return match_frame.family in self._flags


class InAppMatch(FrameMatch):
    def __init__(self, key: str, pattern: str, negated: bool = False):
        super().__init__(key, pattern, negated)
        self._ref_val = get_rule_bool(self.pattern)

    def _positive_frame_match(
        self,
        match_frame: MatchFrame,
        platform: str,
        exception_data: ExceptionData,
        cache: MatchingCache,
    ) -> bool:
        ref_val = self._ref_val
        return ref_val is not None and ref_val == match_frame.in_app


class FunctionMatch(FrameMatch):
    def _positive_frame_match(
        self,
        match_frame: MatchFrame,
        platform: str,
        exception_data: ExceptionData,
        cache: MatchingCache,
    ) -> bool:
        return cached(cache, glob_match, match_frame.function, self._compiled_pattern)


class FrameFieldMatch(FrameMatch):
    @staticmethod
    def get_value(frame: MatchFrame) -> Any:
        raise NotImplementedError()

    def _positive_frame_match(
        self,
        match_frame: MatchFrame,
        platform: str,
        exception_data: ExceptionData,
        cache: MatchingCache,
    ) -> bool:
        field = self.get_value(match_frame)
        if field is None:
            return False

        return cached(cache, glob_match, field, self._compiled_pattern)


class ModuleMatch(FrameFieldMatch):
    @staticmethod
    def get_value(frame: MatchFrame) -> Any:
        return frame.module


class CategoryMatch(FrameFieldMatch):
    @staticmethod
    def get_value(frame: MatchFrame) -> Any:
        return frame.category


class ExceptionFieldMatch(FrameMatch):

    field_path: ClassVar[Sequence[str]]

    def _positive_frame_match(
        self,
        match_frame: MatchFrame,
        platform: str,
        exception_data: ExceptionData,
        cache: MatchingCache,
    ) -> bool:
        field = get_path(exception_data, *self.field_path) or "<unknown>"

        return cached(cache, glob_match, field, self._compiled_pattern)


class ExceptionTypeMatch(ExceptionFieldMatch):

    field_path = ["type"]


class ExceptionValueMatch(ExceptionFieldMatch):

    field_path = ["value"]


class ExceptionMechanismMatch(ExceptionFieldMatch):

    field_path = ["mechanism", "type"]


class CallerMatch(Match):
    def __init__(self, caller: Match):
        self.caller = caller

    @property
    def description(self) -> str:
        return f"[ {self.caller.description} ] |"

    def _to_config_structure(self, version: int) -> str:
        return f"[{self.caller._to_config_structure(version)}]|"

    def matches_frame(
        self,
        frames: Sequence[MatchFrame],
        idx: int,
        platform: str,
        exception_data: ExceptionData,
        cache: MatchingCache,
    ) -> bool:
        return idx > 0 and self.caller.matches_frame(
            frames, idx - 1, platform, exception_data, cache
        )


class CalleeMatch(Match):
    def __init__(self, caller: Match):
        self.caller = caller

    @property
    def description(self) -> str:
        return f"| [ {self.caller.description} ]"

    def _to_config_structure(self, version: int) -> str:
        return f"|[{self.caller._to_config_structure(version)}]"

    def matches_frame(
        self,
        frames: Sequence[MatchFrame],
        idx: int,
        platform: str,
        exception_data: ExceptionData,
        cache: MatchingCache,
    ) -> bool:
        return idx < len(frames) - 1 and self.caller.matches_frame(
            frames, idx + 1, platform, exception_data, cache
        )
