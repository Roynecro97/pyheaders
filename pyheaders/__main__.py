#!/usr/bin/env python

import re  # move me
import sys
import argparse

from . import compiler

from .cpp.scope import Scope
from .cpp.scope import split as split_scope
from .cpp.enum import Enum

try:
    import argcomplete
except ImportError:
    pass

LINE = '|    '
ITEM = '+--- '
LAST = '`--- '
NONE = '     '

ANONYMOUS_ENUM = '[anonymous]'


def _tree(scope, indent):
    for i, item in enumerate(scope):
        if i == len(scope) - 1:
            prefix = indent + LAST
            next_prefix = indent + NONE
        else:
            prefix = indent + ITEM
            next_prefix = indent + LINE

        if isinstance(scope[item], Scope):
            print(prefix + item)
            _tree(scope[item], next_prefix)
        else:
            print(prefix + item, '=', scope[item])


def tree(scope, indent=''):
    '''
    Print the scope like a tree.
    '''
    print(indent + '(global scope)')
    _tree(scope, indent)


def _pretty_print(scope, indent):
    for item in scope:
        if isinstance(scope[item], Scope):
            print(indent + item, '{')
            _pretty_print(scope[item], indent + '    ')
            print(indent + '}')
        else:
            print(indent + item, '=', scope[item])


def pretty_print(scope, indent=''):
    '''
    Print like a scope.
    '''
    _pretty_print(scope, indent)


def enums(scope, starting_path=''):
    item_path = starting_path and (starting_path + Scope.SEP)
    for item in scope:
        if isinstance(scope[item], Scope):
            for enum in enums(scope[item], starting_path=item_path + item):  # !!!
                yield enum
        elif isinstance(scope[item], Enum):
            yield item_path + item, scope[item]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('file')

    if 'argcomplete' in sys.modules:
        argcomplete.autocomplete(parser)

    args, extra_args = parser.parse_known_args()

    if not compiler.check_syntax(args.file, extra_args):
        return -1

    consts_txt = compiler.run_plugin(args.file, extra_args)

    global_scope = Scope()
    current_enum = Enum('kaki') and None
    enum_starting = False
    anonymous_in_scope = {}

    for i, line in enumerate(consts_txt.split('\n')):
        if enum_starting:
            if not re.match(r'\s*{\s*', line):
                raise ValueError("Unexpected plugin output in line {}: {!r}".format(i, line))  # TODO: improve
            enum_starting = False
        else:
            value_match = re.match(r'\s*(?P<name>(?:\w|::)+)\s*=\s*(?P<value>-?\d+)\s*,?\s*', line)
            enum_match = re.match(r'\s*enum\s+(?P<name>\S+)\s*', line)

            if value_match:
                name = value_match.groupdict()['name']
                value = int(value_match.groupdict()['value'])
                global_scope[name] = value
                if current_enum is not None:
                    current_enum[split_scope(name)[1]] = value
            elif enum_match:
                name = enum_match.groupdict()['name']
                enum_scope, enum_name = split_scope(name)
                if enum_name == ANONYMOUS_ENUM:
                    anonymous_num = anonymous_in_scope.get(enum_scope, 0)
                    number_suffix = '`{}'.format(anonymous_num)
                    name += number_suffix
                    anonymous_in_scope[enum_scope] = anonymous_num + 1
                current_enum = Enum(enum_name)
                global_scope[name] = current_enum
                enum_starting = True
            elif re.match(r'\s*}\s*', line):
                if current_enum is None:
                    raise ValueError("Unexpected plugin output in line {}: {!r}".format(i, line))  # TODO: improve
                current_enum = None
            elif re.match(r'\s*', line):
                pass
            else:
                raise ValueError("Unexpected plugin output in line {}: {!r}".format(i, line))  # TODO: improve

    pretty_print(global_scope)
    print()
    print('\n'.join('{}\t[{}]'.format(name, ', '.join(val)) for name, val in enums(global_scope)))


if __name__ == '__main__':
    exit(main() or 0)
