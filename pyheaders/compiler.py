#!/usr/bin/env python

import os
import re
import sys
import json
import subprocess

# When set to False compiler errors are silent
VERBOSE = True


def find_git_env(start_at=None):
    '''
    Finds the git environment containing the pwd.
    Returns None if not environment is found.

    TODO: improve docs
    '''
    if start_at is None:
        start_at = os.curdir

    prev_dir = None
    curr_dir = os.path.abspath(start_at)
    while '.git' not in os.listdir(curr_dir):
        prev_dir = curr_dir
        curr_dir = os.path.abspath(os.path.join(curr_dir, os.pardir))
        if curr_dir == prev_dir:
            break
    else:
        return curr_dir


def get_compile_commands(start_at=None):
    '''
    TODO: docs
    '''
    env = find_git_env(start_at)
    cmds_file = os.path.join(env or os.curdir, 'compile_commands.json')

    if env and os.path.isfile(cmds_file):
        with open(cmds_file) as cmds_fd:
            return json.load(cmds_fd)
    elif os.path.isfile('compile_commands.json'):
        with open(cmds_file) as cmds_fd:
            return json.load(cmds_fd)
    else:
        return {}


def find_in_cmds(filename, cmds):
    '''
    find_in_cmds(filename, cmds) -> dict

    Find the commands to compile `filename`.
    `None` is returned if no such command is found.

    @param filename The file to look for.
    @param cmds     A compile_commands.json style dictionary.
    '''
    for cmd in cmds:
        if cmd['file'] == filename:
            return cmd


# Pattern for strip_cmds()
_PATTERNS = [
    r'^cc\s+',
    r'(?:^|\s+)-c(?=\s+)',
    r'(?:^|\s+)-o\s+\.objects/.*?\.o(?=\s+)',
    r'(?:^|\s+)-g\d?(?=\s+)',
    r'(?:^|\s+)-O\d?(?=\s+)'
]


def strip_cmds(cmd):
    '''
    strip_cmds(cmd) -> str

    Removes unwanted flags from `command` field in the compile command.

    @param cmd The entire command dictionary.
    '''
    command = cmd['command']

    for pattern in _PATTERNS:
        command = re.sub(pattern, '', command)

    command = re.sub(r'\\"', '"', command)
    return re.sub(r'\s+' + os.path.relpath(cmd['file'], start=cmd['directory']) + r'$', '', command).strip()


def common_flags(cmds):
    '''
    common_flags(cmds) -> [str]

    Gets all flags that are used for all files.

    @param cmds The compile commands.
    '''
    flags = None
    for cmd in cmds:
        cmd_flags = set(strip_cmds(cmd).split())
        flags = flags & cmd_flags if flags is not None else cmd_flags
    return list(flags)


def get_params(filename, extra_args):
    '''
    get_params(filename, extra_args) -> (str, [str])

    Gets compilation parameters for `filename`.
    Returns the compile commands' args for `filename` and the compilation directory.

    @param filename The name of the file.
    @param extra_args Additional args to append to the compile commands' flags.
    '''
    cmds = get_compile_commands(os.path.dirname(filename))

    filename = os.path.abspath(filename)
    cmd = find_in_cmds(filename, cmds) or find_in_cmds(os.path.splitext(filename)[0] + '.cpp', cmds)
    if cmd:
        return cmd['directory'], strip_cmds(cmd).split() + extra_args
    elif cmds:
        return cmds[0]['directory'], common_flags(cmds) + extra_args
    return os.curdir, extra_args


def check_syntax(filename, extra_args):
    '''
    check_syntax(filename, extra_args) -> bool
    Checks for syntax errors in `filename` using clang's -fsyntax-only.

    @param filename The name of the file.
    @param extra_args Additional args to append to the compile commands' flags.
    '''
    filename = os.path.abspath(filename)
    org_dir = os.path.abspath(os.curdir)

    run_dir, args = get_params(filename, extra_args)

    os.chdir(run_dir)
    exit_code = subprocess.call(['clang-10', '-fsyntax-only', '-x', 'c++'] + args + [os.path.relpath(filename)],
                                stderr=None if VERBOSE else open(os.devnull, 'wb'))

    os.chdir(org_dir)
    return exit_code == 0


def preprocess(filename, extra_args):
    '''
    preprocess(filename, extra_args) -> str

    Preprocess `filename`.

    @param filename The name of the file.
    @param extra_args Additional args to append to the compile commands' flags.
    '''
    filename = os.path.abspath(filename)
    org_dir = os.path.abspath(os.curdir)

    try:
        run_dir, args = get_params(filename, extra_args)

        os.chdir(run_dir)
        preprocessed = subprocess.check_output(['clang-10', '-E', '-x', 'c++'] + args + [os.path.relpath(filename)],
                                               stderr=None if VERBOSE else open(os.devnull, 'wb')).decode()
    except subprocess.CalledProcessError as err:
        print("error: {!r} exited with {}.".format(err.cmd[0], err.returncode), file=sys.stderr)
        print("command: {}".format(' '.join(err.cmd)), file=sys.stderr)
    finally:
        os.chdir(org_dir)

    # Remove preprocessor markings
    preprocessed = re.sub(r'^#.*$', '', preprocess, flags=re.M)

    # Trim whitespace
    preprocessed = re.sub(r'\n\s*\n', '\n', preprocess, flags=re.M | re.S)

    return preprocessed


def run_plugin(filename, extra_args):
    '''
    preprocess(filename, extra_args) -> str

    Preprocess `filename`.

    @param filename The name of the file.
    @param extra_args Additional args to append to the compile commands' flags.
    '''
    filename = os.path.abspath(filename)
    plugin_lib = os.path.abspath(os.path.join(os.path.dirname(
        os.path.abspath(__file__)), 'ConstantsDumperClangPlugin.so'))

    # TODO: Refactor this

    org_dir = os.path.abspath(os.curdir)

    try:
        run_dir, args = get_params(filename, extra_args)

        os.chdir(run_dir)
        plugin_output = subprocess.check_output(
            [
                'clang-10', '-x', 'c++',
                '-c', '-Xclang', '-load', '-Xclang', plugin_lib, '-Xclang', '-plugin', '-Xclang', 'ConstantsDumperClangPlugin'
            ] + args + [os.path.relpath(filename)],
            stderr=None if VERBOSE else open(os.devnull, 'wb')).decode()
    except subprocess.CalledProcessError as err:
        print("error: {!r} exited with {}.".format(err.cmd[0], err.returncode), file=sys.stderr)
        print("command: {}".format(' '.join(err.cmd)), file=sys.stderr)
    finally:
        os.chdir(org_dir)

    return plugin_output
