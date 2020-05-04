#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK
'''
The main entry for the pyheaders package to allow it to run as a command-line tool.
'''
import sys
import argparse

from . import load_path
from .compiler import PluginError
from .cpp import Scope
from .utils import enums, pretty_print, tree

try:
    import argcomplete
except ImportError:
    pass


def handle_print(args, global_scope):
    '''
    Handle the `print` subparser.
    '''
    if args.tree:
        tree(global_scope)
    elif args.enums:
        print('\n'.join(f'{name}\t[{", ".join(val)}]' for name, val in enums(global_scope)))
    else:
        pretty_print(global_scope)

    return True


def handle_get(args, global_scope):
    '''
    Handle the `get` subparser.
    '''
    found = False
    for var_type, var_name in args.items:
        if var_name in global_scope:
            found = True
            if args.show_names:
                print(f'{var_name}=', end="")

            if var_type == "const":
                print(f'{global_scope[var_name]!r}')
            elif var_type == "enum":
                print(f'[{", ".join(global_scope[var_name])}]')

    return found


class AppendWithName(argparse.Action):
    '''
    Action that appends the given flag values to a list in a tuple with the flag name.

    f.e. when using `program --flag1 val1 --flag2 val2 --flag1 val3`,
    The result list will contain: [("flag1", val1), ("flag2", val2), "flag1", val3]
    '''
    def __call__(self, parser, namespace, values, option_string=None):
        items = getattr(namespace, self.dest, None)
        items = [] if items is None else items[:]
        items.append((option_string.lstrip(parser.prefix_chars), values))
        setattr(namespace, self.dest, items)


def main():
    '''
    pyheaders' main entrypoint.
    '''
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()

    base_parser = argparse.ArgumentParser(add_help=False)
    base_parser.add_argument('files', metavar='file', nargs='+',
                             help="The files and directories that the constants are loaded from")

    verbosity_flags = base_parser.add_mutually_exclusive_group()
    verbosity_flags.add_argument('--verbose', action='store_true', dest='verbose', help="Show every plugin error")
    verbosity_flags.add_argument('-q', '--quiet', action='store_false', dest='verbose', help="Mute all plugin errors")
    base_parser.set_defaults(verbose=True)

    print_parser = subparsers.add_parser('print', parents=[base_parser],
                                         help="Print all constants in a human readable form")
    print_mode = print_parser.add_mutually_exclusive_group()
    print_mode.add_argument('--tree', action='store_true', help="Print the constants in a tree-like format")
    print_mode.add_argument('--enums', action='store_true', help="Print the enums in enum formats")
    print_parser.set_defaults(cmd=handle_print)

    get_parser = subparsers.add_parser('get', parents=[base_parser], help="Get the values for given items")
    get_parser.add_argument('--const', action=AppendWithName, dest='items',
                            help="The requested items")
    get_parser.add_argument('--enum', action=AppendWithName, dest='items',
                            help="The requested enums")
    get_parser.add_argument('--hide-names', action='store_false', dest='show_names',
                            help="Hide the names of the requested items")
    get_parser.set_defaults(cmd=handle_get)

    if 'argcomplete' in sys.modules:
        argcomplete.autocomplete(parser)

    args, extra_args = parser.parse_known_args()
    try:
        global_scope = Scope()
        for filename in args.files:
            load_path(filename, extra_args, initial_scope=global_scope, verbose=args.verbose)
    except PluginError:
        sys.exit(1)
    success = args.cmd(args, global_scope)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
