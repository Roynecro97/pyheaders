#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK
'''
The main entry for the pyheaders package to allow it to run as a command-line tool.
'''
import sys
import argparse

from . import load_path, SrcData
from .compiler import PluginError, CommandsParser
from .utils import enums, pretty_print, tree

try:
    import argcomplete
except ImportError:
    pass


def handle_print(args, data):
    '''
    Handle the `print` subparser.
    '''
    if args.tree:
        tree(data.scope)
    elif args.enums:
        print('\n'.join(f'{name}\t[{", ".join(val)}]' for name, val in enums(data.scope)))
    elif args.macros:
        print('\n'.join(f'{name}={value}' for name, value in sorted(data.macros.items()) if not name.startswith('_')))
    else:
        pretty_print(data.scope)

    return True


def _var_in_data(var_type, var_name, data):
    if var_type == "macro":
        return var_name in data.macros
    return var_name in data.scope


def handle_get(args, data):
    '''
    Handle the `get` subparser.
    '''
    found = False
    for var_type, var_name in args.items:
        if _var_in_data(var_type, var_name, data):
            found = True
            if args.show_names:
                print(f'{var_name}=', end="")

            if var_type == "const":
                print(f'{data.scope[var_name]!r}')
            elif var_type == "enum":
                print(f'[{", ".join(data.scope[var_name])}]')
            elif var_type == "macro":
                print(f'{data.macros[var_name]}')

    return found


def compile_commands(path):
    '''
    Creates a CommandsParser, used as an argparse argument type
    '''
    return CommandsParser(commands_path=path)


class AppendWithName(argparse.Action):  # pylint: disable=too-few-public-methods
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
    parser = argparse.ArgumentParser(description="A command-line tool for parsing C++ source/header files")
    subparsers = parser.add_subparsers(dest="print/get", required=True)

    base_parser = argparse.ArgumentParser(add_help=False)
    base_parser.add_argument('files', metavar='file', nargs='+',
                             help="The files and directories that the constants are loaded from")
    base_parser.add_argument('--exclude', dest="excludes", action='append',
                             help="The files and directories that will be excluded from the search")
    base_parser.add_argument('--clang-path', help="The full path to the clang executable")

    compile_commands_flags = base_parser.add_mutually_exclusive_group()
    compile_commands_flags.add_argument('--compile-commands', type=compile_commands, dest='commands_parser',
                                        help="The path to the compile commands")
    compile_commands_flags.add_argument('--ignore-cmds', action='store_true', help="Ignore the compile commands")

    verbosity_flags = base_parser.add_mutually_exclusive_group()
    verbosity_flags.add_argument('--verbose', action='store_true', dest='verbose', help="Show every plugin error")
    verbosity_flags.add_argument('-q', '--quiet', action='store_false', dest='verbose', help="Mute all plugin errors")
    base_parser.set_defaults(verbose=True)

    print_parser = subparsers.add_parser('print', parents=[base_parser],
                                         help="Print all constants in a human readable form")
    print_mode = print_parser.add_mutually_exclusive_group()
    print_mode.add_argument('--tree', action='store_true', help="Print the constants in a tree-like format")
    print_mode.add_argument('--enums', action='store_true', help="Print the enums in enum formats")
    print_mode.add_argument('--macros', action='store_true', help="Print the macros after being expanded")
    print_parser.set_defaults(cmd=handle_print)

    get_parser = subparsers.add_parser('get', parents=[base_parser], help="Get the values for given items")
    get_parser.add_argument('--const', action=AppendWithName, dest='items',
                            help="The requested items")
    get_parser.add_argument('--enum', action=AppendWithName, dest='items',
                            help="The requested enums")
    get_parser.add_argument('--macro', action=AppendWithName, dest='items',
                            help="The requested macros")
    get_parser.add_argument('--hide-names', action='store_false', dest='show_names',
                            help="Hide the names of the requested items")
    get_parser.set_defaults(cmd=handle_get)

    if 'argcomplete' in sys.modules:
        argcomplete.autocomplete(parser)

    args, extra_args = parser.parse_known_args()
    try:
        data = load_path(*args.files, extra_args=extra_args, clang_path=args.clang_path, verbose=args.verbose,
                         commands_parser=args.commands_parser, ignore_cmds=args.ignore_cmds, excludes=args.excludes)
    except PluginError:
        sys.exit(1)
    success = args.cmd(args, data)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
