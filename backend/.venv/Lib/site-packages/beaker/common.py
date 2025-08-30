import re
from datetime import timedelta


def to_nanoseconds(dur: str | int | float | timedelta) -> int:
    if isinstance(dur, timedelta):
        return int(dur.total_seconds() * 1_000_000_000)
    elif isinstance(dur, str):
        return parse_duration(dur)
    elif isinstance(dur, (int, float)):
        return int(dur)
    else:
        raise TypeError(f"expected str, int, float, or timedelta, got {type(dur)}")


def parse_duration(dur: str) -> int:
    """
    Parse a duration string into nanoseconds.
    """
    dur_normalized = dur.replace(" ", "").lower()

    matches = list(re.finditer(r"([0-9.e-]+)([a-z]*)", dur_normalized))
    if not matches:
        raise ValueError(f"invalid duration string '{dur}'")

    nanos = 0
    for match in matches:
        value_str, unit = match.group(1), match.group(2)
        try:
            value = float(value_str)
        except ValueError:
            raise ValueError(f"invalid duration string '{dur}'")

        if not unit:
            # assume seconds
            unit = "s"

        if unit in ("ns", "nanosecond", "nanoseconds"):
            # nanoseconds
            nanos += int(value)
        elif unit in ("µs", "microsecond", "microseconds"):
            nanos += int(value * 1_000)
        elif unit in ("ms", "millisecond", "milliseconds"):
            # milliseconds
            nanos += int(value * 1_000_000)
        elif unit in ("s", "sec", "second", "seconds"):
            # seconds
            nanos += int(value * 1_000_000_000)
        elif unit in ("m", "min", "minute", "minutes"):
            # minutes
            nanos += int(value * 60_000_000_000)
        elif unit in ("h", "hr", "hour", "hours"):
            # hours
            nanos += int(value * 3_600_000_000_000)
        else:
            raise ValueError(f"invalid duration string '{dur}'")

    return nanos


def to_lower_camel(s: str) -> str:
    """
    Convert a snake-case string into lower camel case.
    """
    parts = s.split("_")
    out = parts[0] + "".join([p.title() for p in parts[1:]])
    out = re.sub(r"(^|[a-z0-9])Id($|[A-Z0-9])", r"\g<1>ID\g<2>", out)
    return out


def to_snake_case(s: str) -> str:
    """
    Convert a lower camel case strings into snake case.
    """
    if s.islower():
        return s
    s = re.sub(r"(^|[a-z0-9])ID", r"\g<1>Id", s)
    parts = []
    for c in s:
        if c.isupper():
            parts.append("_")
        parts.append(c.lower())
    return "".join(parts)
