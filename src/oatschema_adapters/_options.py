# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import functools
import inspect
import math
import os
import types
import typing
from collections.abc import Callable
from typing import Any, Literal, TypeVar, Union

F = TypeVar("F", bound=Callable[..., Any])

_TRUE = frozenset({"true", "1", "yes", "on"})
_FALSE = frozenset({"false", "0", "no", "off"})
_NONE = frozenset({"none", "null"})
_OPTION_KINDS = (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)


class _NoMatch(Exception):
    pass


def _describe(hint: Any) -> str:
    if hint is type(None):
        return "None"
    if typing.get_origin(hint) is Literal:
        return " or ".join(repr(value) for value in typing.get_args(hint))
    if typing.get_origin(hint) in (Union, types.UnionType):
        return " or ".join(_describe(arg) for arg in typing.get_args(hint))
    if hint is os.PathLike or typing.get_origin(hint) is os.PathLike:
        return "a path"
    return {bool: "true or false", int: "an integer", float: "a number", str: "a string"}.get(hint, str(hint))


def _convert(value: Any, hint: Any) -> Any:
    origin = typing.get_origin(hint)
    if hint is Any:
        return value
    if hint is type(None):
        if value is None or (isinstance(value, str) and value.strip().lower() in _NONE):
            return None
        raise _NoMatch
    if origin is Literal:
        for allowed in typing.get_args(hint):
            if type(value) is type(allowed) and value == allowed:
                return value
        raise _NoMatch
    if origin in (Union, types.UnionType):
        members = typing.get_args(hint)
        ordered = sorted(members, key=lambda member: member is type(None) or member is str)
        if isinstance(value, str) and str in members:
            ordered = [member for member in ordered if member is not type(None)]
        for member in ordered:
            try:
                return _convert(value, member)
            except _NoMatch:
                continue
        raise _NoMatch
    if hint is os.PathLike or origin is os.PathLike:
        if isinstance(value, os.PathLike):
            return value
        raise _NoMatch
    if hint is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            text = value.strip().lower()
            if text in _TRUE:
                return True
            if text in _FALSE:
                return False
        raise _NoMatch
    if hint is int:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, str):
            try:
                return int(value.strip())
            except ValueError:
                raise _NoMatch from None
        raise _NoMatch
    if hint is float:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if math.isfinite(value):
                return value
            raise _NoMatch
        if isinstance(value, str):
            try:
                number = float(value.strip())
            except ValueError:
                raise _NoMatch from None
            if math.isfinite(number):
                return number
        raise _NoMatch
    if hint is str:
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
        raise _NoMatch
    return value


def checked(function: F) -> F:
    """Check and convert a function's options to their annotated types.

    Every parameter after the first is an option. A string is converted to the option's type, so values from a
    command line (``"false"``, ``"0.5"``) work, and a number given for a string option becomes its text. A value that can't be converted raises ``ValueError`` if it was a
    string, and ``TypeError`` otherwise, naming the option. An unknown option raises ``TypeError`` listing the
    known ones.
    """
    signature = inspect.signature(function)
    hints = typing.get_type_hints(function)
    parameters = list(signature.parameters.values())
    options = {
        parameter.name: hints.get(parameter.name, Any)
        for parameter in parameters[1:]
        if parameter.kind in _OPTION_KINDS
    }
    accepts_more = any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters)
    name = function.__name__

    @functools.wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not accepts_more:
            unknown = sorted(set(kwargs) - set(options) - {parameters[0].name})
            if unknown:
                known = ", ".join(options)
                raise TypeError(f"{name}() got unknown option(s) {', '.join(map(repr, unknown))}; options: {known}")
        bound = signature.bind(*args, **kwargs)
        for option, value in bound.arguments.items():
            if option not in options:
                continue
            try:
                bound.arguments[option] = _convert(value, options[option])
            except _NoMatch:
                expected = _describe(options[option])
                error = ValueError if isinstance(value, str) else TypeError
                raise error(f"{name}() option {option!r} must be {expected}, not {value!r}") from None
        return function(*bound.args, **bound.kwargs)

    return typing.cast(F, wrapper)
