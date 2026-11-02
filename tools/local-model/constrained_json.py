"""Decide whether text can still become a JSON document matching a pydantic-style JSON Schema.

Standard library only, so it is testable without MLX. Greedy decoding uses it to take the most
likely token that keeps the reply viable. It enforces shape: required keys, enums, types and
nesting. It cannot enforce cross-field rules, and it does not make an answer true: the application
still validates every reply and every evidence reference afterwards.
"""

_WHITESPACE = " \t\n\r"
_INCOMPLETE = -1
_ESCAPES = '"\\/bfnrt'
_DIGITS = "0123456789"
_HEX = "0123456789abcdefABCDEF"


def _skip(text, index):
    while index < len(text) and text[index] in _WHITESPACE:
        index += 1
    return index


def _literal(word, text, index):
    piece = text[index : index + len(word)]
    if piece == word:
        return [index + len(word)]
    return [_INCOMPLETE] if word.startswith(piece) and index + len(piece) == len(text) else []


def _string(text, index):
    """End index of the string at ``index``, _INCOMPLETE if it runs out, None if it is invalid."""
    if index >= len(text):
        return _INCOMPLETE
    if text[index] != '"':
        return None
    index += 1
    while index < len(text):
        character = text[index]
        if character == '"':
            return index + 1
        if ord(character) < 0x20:
            return None
        if character != "\\":
            index += 1
            continue
        if index + 1 == len(text):
            return _INCOMPLETE
        escaped = text[index + 1]
        if escaped == "u":
            digits = text[index + 2 : index + 6]
            if any(digit not in _HEX for digit in digits):
                return None
            if len(digits) < 4:
                return _INCOMPLETE
            index += 6
        elif escaped in _ESCAPES:
            index += 2
        else:
            return None
    return _INCOMPLETE


def _number(text, index, integer):
    start = index
    if index < len(text) and text[index] == "-":
        index += 1
    if index == len(text):
        return [_INCOMPLETE]
    if text[index] not in _DIGITS:
        return []
    if text[index] == "0":
        index += 1
    else:
        while index < len(text) and text[index] in _DIGITS:
            index += 1
    if not integer:
        if index < len(text) and text[index] == ".":
            index += 1
            if index == len(text):
                return [_INCOMPLETE]
            if text[index] not in _DIGITS:
                return []
            while index < len(text) and text[index] in _DIGITS:
                index += 1
        if index < len(text) and text[index] in "eE":
            index += 1
            if index < len(text) and text[index] in "+-":
                index += 1
            if index == len(text):
                return [_INCOMPLETE]
            if text[index] not in _DIGITS:
                return []
            while index < len(text) and text[index] in _DIGITS:
                index += 1
    # A number at the very end may continue with more digits, or may already be complete.
    return [_INCOMPLETE, index] if index == len(text) and index > start else [index]


class SchemaMatcher:
    """Recursive descent over the schema subset pydantic emits for the two proposal models."""

    def __init__(self, schema):
        self.root = schema
        self.definitions = schema.get("$defs", {})

    def _resolve(self, schema):
        while "$ref" in schema:
            schema = self.definitions[schema["$ref"].rsplit("/", 1)[1]]
        return schema

    def _value(self, schema, text, index):
        index = _skip(text, index)
        if index == len(text):
            return [_INCOMPLETE]
        schema = self._resolve(schema)
        if "anyOf" in schema:
            return self._alternatives(schema["anyOf"], text, index)
        if "const" in schema:
            return self._enum([schema["const"]], text, index)
        if "enum" in schema:
            return self._enum(schema["enum"], text, index)
        kind = schema.get("type")
        if kind == "object":
            return self._object(schema, text, index)
        if kind == "array":
            return self._array(schema, text, index)
        if kind == "string":
            end = _string(text, index)
            return [] if end is None else [end]
        if kind in {"integer", "number"}:
            return _number(text, index, kind == "integer")
        if kind == "boolean":
            return _literal("true", text, index) + _literal("false", text, index)
        if kind == "null":
            return _literal("null", text, index)
        # No type: any JSON value, as pydantic writes for JsonValue.
        return self._any(text, index)

    def _alternatives(self, options, text, index):
        ends = []
        for option in options:
            ends.extend(self._value(option, text, index))
        return list(dict.fromkeys(ends))

    def _any(self, text, index):
        character = text[index]
        if character == "{":
            return self._object({"type": "object"}, text, index)
        if character == "[":
            return self._array({"type": "array"}, text, index)
        if character == '"':
            end = _string(text, index)
            return [] if end is None else [end]
        if character in "-0123456789":
            return _number(text, index, False)
        ends = []
        for word in ("true", "false", "null"):
            ends.extend(_literal(word, text, index))
        return ends

    def _enum(self, values, text, index):
        ends = []
        for value in values:
            if value is None:
                ends.extend(_literal("null", text, index))
            elif isinstance(value, bool):
                ends.extend(_literal("true" if value else "false", text, index))
            elif isinstance(value, str):
                # Both quotes are part of the value; an enum never holds a character to escape.
                ends.extend(_literal(f'"{value}"', text, index))
            else:
                ends.extend(_literal(str(value), text, index))
        return list(dict.fromkeys(ends))

    def _object(self, schema, text, index):
        if text[index] != "{":
            return []
        properties = schema.get("properties")
        closed = properties is not None and schema.get("additionalProperties") is False
        required = set(schema.get("required", ()))
        index = _skip(text, index + 1)
        if index == len(text):
            return [_INCOMPLETE]
        seen = set()
        if text[index] == "}":
            return [index + 1] if not required else []
        while True:
            end = _string(text, index)
            if end is None:
                return []
            if end == _INCOMPLETE:
                return (
                    [_INCOMPLETE]
                    if self._key_viable(text[index:], properties, closed, seen)
                    else []
                )
            key = _plain_key(text[index:end])
            if key in seen or (closed and key not in properties):
                return []
            seen.add(key)
            index = _skip(text, end)
            if index == len(text):
                return [_INCOMPLETE]
            if text[index] != ":":
                return []
            value_schema = (properties or {}).get(key, {})
            outcome = None
            for value_end in self._value(value_schema, text, index + 1):
                if value_end == _INCOMPLETE:
                    outcome = _INCOMPLETE
                    continue
                after = _skip(text, value_end)
                if after == len(text):
                    outcome = _INCOMPLETE if outcome is None else outcome
                    continue
                if text[after] in ",}":
                    outcome = after
                    break
            if outcome is None:
                return []
            if outcome == _INCOMPLETE:
                return [_INCOMPLETE]
            if text[outcome] == "}":
                return [outcome + 1] if required <= seen else []
            index = _skip(text, outcome + 1)
            if index == len(text):
                return [_INCOMPLETE]

    @staticmethod
    def _key_viable(partial, properties, closed, seen):
        if not closed:
            return True
        return any(key not in seen and f'"{key}"'.startswith(partial) for key in properties)

    def _array(self, schema, text, index):
        if text[index] != "[":
            return []
        items = schema.get("items", {})
        minimum = schema.get("minItems", 0)
        maximum = schema.get("maxItems")
        index = _skip(text, index + 1)
        if index == len(text):
            return [_INCOMPLETE]
        if text[index] == "]":
            return [index + 1] if minimum == 0 else []
        count = 0
        while True:
            if maximum is not None and count >= maximum:
                return []
            outcome = None
            for value_end in self._value(items, text, index):
                if value_end == _INCOMPLETE:
                    outcome = _INCOMPLETE
                    continue
                after = _skip(text, value_end)
                if after == len(text):
                    outcome = _INCOMPLETE if outcome is None else outcome
                    continue
                if text[after] in ",]":
                    outcome = after
                    break
            if outcome is None:
                return []
            if outcome == _INCOMPLETE:
                return [_INCOMPLETE]
            count += 1
            if text[outcome] == "]":
                return [outcome + 1] if count >= minimum else []
            index = _skip(text, outcome + 1)
            if index == len(text):
                return [_INCOMPLETE]

    def viable(self, text):
        """The text is a prefix of some document this schema accepts."""
        return any(
            end == _INCOMPLETE or _skip(text, end) == len(text)
            for end in self._value(self.root, text, 0)
        )

    def complete(self, text):
        """The text already is a whole document this schema accepts."""
        return any(
            end != _INCOMPLETE and _skip(text, end) == len(text)
            for end in self._value(self.root, text, 0)
        )


def _plain_key(quoted):
    # Schema keys never need escapes, so an escaped key simply matches no property.
    return quoted[1:-1]


def choose_token(matcher, text, ranked_tokens, decode, stop_tokens):
    """The most likely token that keeps the reply viable, or None if no candidate does.

    ``ranked_tokens`` is most likely first. A stop token is allowed only once the reply is whole,
    and is the only choice then: a finished document has nothing valid to add but whitespace.
    """
    whole = matcher.complete(text)
    for token in ranked_tokens:
        if token in stop_tokens:
            if whole:
                return token
            continue
        if whole:
            continue
        piece = decode(token)
        # Empty or partial multi-byte output cannot be checked, so it is not taken.
        if piece and "�" not in piece and matcher.viable(text + piece):
            return token
    return None
