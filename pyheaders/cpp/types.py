'''
Support utilities for value types and various utilities for working with type names
and constructor parameters.
'''


import re
import sys

from typing import Any, AnyStr, Dict, List, Optional, Text, Tuple

AnyScope = Dict[Text, Any]

PARENS_START = '('
PARENS_END = ')'
TEMPLATE_START = '<'
TEMPLATE_END = '>'

ALL_BRACKETS = {PARENS_START: PARENS_END, '[': ']', '{': '}', TEMPLATE_START: TEMPLATE_END}
assert all(len(start) == len(end) == 1 for start, end in ALL_BRACKETS.items())


def has_valid_brackets(txt: Text, brackets: Dict[Text, Text] = None) -> bool:
    '''
    Check if all brackets in ``txt`` are closed.
    '''
    if brackets is None:
        brackets = ALL_BRACKETS
    assert len(brackets) == len(set(brackets.values())), "The same close bracket should not be used for 2 open brackets"

    r_brackets = {end: begin for begin, end in brackets.items()}
    bracket_stack = []

    for char in txt:
        if char in brackets:
            bracket_stack.append(char)
        if char in r_brackets:
            # Close bracket without a matching open
            if not bracket_stack or bracket_stack.pop() != r_brackets[char]:
                return False
    return True


def contextual_split(txt: Text, sep: Text = ',', brackets: Dict[Text, Text] = None) -> List[Text]:
    '''
    Split contextually and remove redundant whitespaces.
    '''
    if brackets is None:
        brackets = ALL_BRACKETS
    assert len(brackets) == len(set(brackets.values())), "The same close bracket should not be used for 2 open brackets"

    r_brackets = {end: begin for begin, end in brackets.items()}
    bracket_stack = []

    res = []
    for char in txt:
        if char in brackets:
            bracket_stack.append(char)
        if char in r_brackets:
            if bracket_stack[-1] != r_brackets[char]:
                raise ValueError(f"unexpected {char!r}")
            bracket_stack.pop()

        if char == sep and len(bracket_stack) == 0:
            res.append('')
        elif res:
            res[-1] += char
        else:
            res.append(char)

    return [part.strip() for part in res]


def _func_split(call_string: Text) -> Tuple[Text, Text]:
    '''
    Split a function (a constructor call) from its parameters.
    This assumes the ``call_string`` is valid.

    Returns (str, str) of (func_name, params)
    '''

    assert call_string.endswith(PARENS_END) and call_string.count(PARENS_START) == call_string.count(PARENS_END)

    # Find parameters start
    parens_level = 0
    for i in range(len(call_string) - 1, -1, -1):  # [len(call_string) - 1, 0]
        if call_string[i] == PARENS_END:
            parens_level += 1
        elif call_string[i] == PARENS_START:
            parens_level -= 1

        # We will not reach negative parens_level because call_string ends with PARENS_END
        if parens_level == 0:
            params_start = i
            break
    else:
        raise ValueError(f"Invalid C++ function call: {call_string!r}")

    return call_string[:params_start], call_string[params_start + 1:-1]


def remove_template(name):
    '''
    Remove the template parameters from a name.
    '''
    res = ''
    in_template = 0
    for char in name:
        if char == TEMPLATE_START:
            in_template += 1
        elif char == TEMPLATE_END:
            if in_template == 0:
                raise ValueError(f"unexpected {char!r}")
            in_template -= 1
        elif in_template == 0:
            res += char
    return res


def wchar_t(value: int) -> Text:
    '''
    Default wchar_t decoder. Used for single wchar_t values (characters, not strings).
    This is equivalent to `chr(value)`.
    '''
    return chr(value)


def wchar_string(*values: Text) -> Text:
    '''
    Default wchar_t strings decoder. Used for wchar_t-base string values.
    This is equivalent to `''.join(values)`.
    '''
    return ''.join(values)


def _char_type(name: Text, encoding: Text = 'utf-8'):
    encoding_match = re.match(r'^utf-?(?P<size>\d+)$', encoding, flags=re.I)
    if not encoding_match:
        raise ValueError
    char_size = int(encoding_match.group('size')) // 8

    def _decoder(value: int) -> Text:
        try:
            return value.to_bytes(char_size, sys.byteorder).decode(encoding)
        except ValueError:
            return value.to_bytes(char_size, sys.byteorder)

    _decoder.__name__ = _decoder.__qualname__ = name

    return _decoder


def _str_type(name: Text, encoding: Text = 'utf-8'):
    def _mass_decoder(*values: AnyStr) -> Text:
        if all(isinstance(value, str) for value in values):
            return ''.join(values)

        result = ''
        temp = b''
        for value in values:
            if isinstance(value, str):
                result += temp.decode(encoding) + value
                temp = b''
            else:
                temp += value
        return result + temp.decode(encoding)

    _mass_decoder.__name__ = _mass_decoder.__qualname__ = f'{name}[]'
    return _mass_decoder


def unknown_type(*fields):
    '''
    Fallback for unrecognized type names.
    Returns a tuple of the arguments.
    For single field types, return the field itself.
    '''
    if len(fields) == 1:
        return fields[0]
    return fields


DEFAULT_TYPES = {
    'wchar_t': wchar_t,
    'char8_t': _char_type('char8_t', 'utf-8'),
    'char16_t': _char_type('char16_t', 'utf-16'),
    'char32_t': _char_type('char32_t', 'utf-32'),
    # Strings
    'wchar_t[]': wchar_string,
    'char8_t[]': _str_type('char8_t', 'utf-8'),
    'char16_t[]': _str_type('char16_t', 'utf-16'),
    'char32_t[]': _str_type('char32_t', 'utf-32'),
}
DEFAULT_TYPES['wchar_t[]'].__name__ = DEFAULT_TYPES['wchar_t[]'].__qualname__ = 'wchar_t[]'


def parse_value(raw_value: Text, /, scope: Optional[AnyScope] = None) -> Any:
    '''
    Parse a single value, recursively.

    ``scope`` can be provided to add additional types or override the default char types.
    Note that all string types are only called for array-like strings. For example, ``wchar_t[]``
    will be called for `const wchar_t[] my_string = L"hello"` but not for `const wchar_t* my_string = L"hello"`.
    '''
    if scope is None:
        scope = {}

    last_match: Optional[re.Match]

    def match(pattern: Text, flags=0):
        nonlocal last_match
        last_match = re.match(pattern, raw_value, flags=flags)
        return last_match

    # Any integer
    if match(r'^-?\d+$'):
        return int(last_match.group())

    # Any floating-point
    if match(r'^-?\d+\.\d+e[+-]?\d+$'):
        return float(last_match.group())

    # char or string
    if match(r'''^(?P<quote>'|").*(?P=quote)$'''):
        # Reevaluate escaped characters
        return eval(last_match.group())  # pylint: disable=eval-used

    # bool
    if match(r'^(true|false)$', flags=re.I):
        return last_match.group().lower() == 'true'

    # Arrays
    if match(r'^\((?P<elements>.*)\)$'):
        if has_valid_brackets(elements := last_match.group('elements')):
            return [parse_value(element, scope) for element in contextual_split(elements)]

    # Named types
    if match(r'^(?P<type>.+?)\((?P<params>.*)\)$'):
        typename, params = _func_split(last_match.group())
        params = (parse_value(param, scope) for param in contextual_split(params))

        def get_type(typename: Text, /, default=None):
            return scope.get(typename, DEFAULT_TYPES.get(typename, default))

        type_func = get_type(typename)

        # Couldn't find type, try without templates and default to a simple tuple
        if type_func is None:
            type_func = get_type(remove_template(typename), default=unknown_type)

        try:
            return type_func(*params)
        except ValueError:
            return unknown_type(params)

    # Give up and use the raw value
    return raw_value
