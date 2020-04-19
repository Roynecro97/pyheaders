#!/usr/bin/env python
'''
The main entry for the pyheaders package to allow it to run as a command-line tool.
'''
import sys
import argparse

from . import load_path
from .utils import enums, pretty_print, tree

try:
    import argcomplete
except ImportError:
    pass


def main():
    '''
    pyheaders' main entrypoint.
    '''
    parser = argparse.ArgumentParser()
    parser.add_argument('file')

    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--tree', action='store_true')
    actions.add_argument('--print', action='store_true')
    actions.add_argument('--get', action='append')

    verbosity_flags = parser.add_mutually_exclusive_group()
    verbosity_flags.add_argument('--verbose', action='store_true', dest='verbose')
    verbosity_flags.add_argument('-q', '--quiet', action='store_false', dest='verbose')
    parser.set_defaults(verbose=True)

    if 'argcomplete' in sys.modules:
        argcomplete.autocomplete(parser)

    args, extra_args = parser.parse_known_args()

    global_scope = load_path(args.file, extra_args, verbose=args.verbose)

    if args.tree:
        tree(global_scope)
    elif args.print:
        pretty_print(global_scope)
        # print()
        # print('\n'.join('{}\t[{}]'.format(name, ', '.join(val)) for name, val in enums(global_scope)))
    else:  # get
        found = False
        if len(args.get) == 1:
            item = args.get[0]
            if item in global_scope:
                found = True
                print(repr(global_scope[item]))
        else:
            for item in args.get:
                if item in global_scope:
                    found = True
                    print(f'{item}={global_scope[item]!r}')
        sys.exit(0 if found else 1)


if __name__ == '__main__':
    main()
