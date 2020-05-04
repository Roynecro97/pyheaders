'''
The main entry for the pyheaders package to allow it to run as a command-line tool.
'''
from typing import Iterable, Text, Tuple

from .cpp import Enum, Scope

_TREE_LINE = '|    '
_TREE_ITEM = '+--- '
_TREE_LAST = '`--- '
_TREE_NONE = '     '


def _tree(scope: Scope, indent: Text):
    for i, item in enumerate(scope):
        if i == len(scope) - 1:
            prefix = indent + _TREE_LAST
            next_prefix = indent + _TREE_NONE
        else:
            prefix = indent + _TREE_ITEM
            next_prefix = indent + _TREE_LINE

        if isinstance(scope[item], Scope):
            if scope[item]:
                print(prefix + item)
                _tree(scope[item], next_prefix)
        elif isinstance(scope[item], Enum):
            print(prefix + item, '(enum)')
            _tree(scope[item], next_prefix)
        else:
            print(prefix + item, '=', repr(scope[item]))


def tree(scope: Scope, indent: Text = ''):
    '''
    Print a scope in a human readable form as a tree.

    @param scope    The scope to print.
    @param indent   An initial indent to give everything. (default: '')
    '''
    print(indent + '(global scope)')
    _tree(scope, indent)


_PRETTY_PRINT_INDENT = ' ' * 4


def pretty_print(scope: Scope, indent: Text = ''):
    '''
    Print a scope in a human readable form as pseudo code.

    @param scope    The scope to print.
    @param indent   An initial indent to give everything. (default: '')
    '''
    for item in scope:
        if isinstance(scope[item], Scope):
            if scope[item]:
                print(indent + item, '{')
                pretty_print(scope[item], indent + _PRETTY_PRINT_INDENT)
                print(indent + '}')
        elif isinstance(scope[item], Enum):
            print(indent + 'enum', item, '{')
            pretty_print(scope[item], indent + _PRETTY_PRINT_INDENT)
            print(indent + '}')
        else:
            print(indent + item, '=', repr(scope[item]))


def enums(scope: Scope) -> Iterable[Tuple[Text, Enum]]:
    '''
    Gets an iterator to all enums in a scope.

    @param scope    The scope to scan.

    @returns an iterable of (str, Enum) pairs.
    '''
    for item in scope:
        if isinstance(scope[item], Scope):
            for name, enum in enums(scope[item]):
                yield f"{item}{Scope.SEP}{name}", enum
        elif isinstance(scope[item], Enum):
            yield item, scope[item]
