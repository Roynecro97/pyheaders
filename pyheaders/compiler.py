'''
Implements utils for running the compiler and parsing clang's compile_commands.json.
'''
import json
import os
import re
import shlex
import subprocess
import sys

from contextlib import contextmanager
from functools import lru_cache
from itertools import chain
from typing import AnyStr, Dict, Iterable, List, Pattern, Text, Tuple
from warnings import warn


CompileCommandsEntry = Dict[Text, Text]
CompileCommands = List[CompileCommandsEntry]


class PluginError(subprocess.CalledProcessError):
    '''
    Raised to indicate that the plugin process failed.
    '''

    def __init__(self, proc: subprocess.CompletedProcess):
        super().__init__(returncode=proc.returncode, cmd=shlex.join(proc.args), output=proc.stdout, stderr=proc.stderr)


class MissingCompileCommands(UserWarning):
    '''
    Warns that the provided compile commands is missing and therefore ignored.
    '''


@contextmanager
def directory(dirname: AnyStr):
    '''
    Changes the current directory to `dirname`.

    @param dirname The path to change into.

    Typical usage:

        with directory(<dirname>):
            <code>

    Can also be used as a decorator to make a function always run in
    a specific directory:

        @directory(<dirname>)
        def some_func(<arguments>):
            <body>

    Equivalent to this:

        def some_func(<arguments>):
            with directory(<dirname>):
                <body>
    '''
    old_cwd = os.getcwd()
    os.chdir(dirname)
    try:
        yield
    finally:
        os.chdir(old_cwd)


CPP_SOURCE_FILES_EXTENSIONS = (
    '.cpp',
    '.cc',
    '.cxx',
    '.C',
    '.CPP',
    '.cp',
    '.c++',
    '.ii'  # C++ code that will not be pre-processed
)

C_SOURCE_FILES_EXTENSIONS = (
    '.c',
    '.i'  # C code that will not be pre-processed
)

HEADER_FILES_EXTENSIONS = (
    '.h',
    # Only C++
    '.hpp',
    '.hh',
    '.hxx',
    '.H',
    '.HPP',
    '.hp',
    '.h++',
    '.tcc'
)

ALL_C_CPP_FILES_EXTENSIONS = CPP_SOURCE_FILES_EXTENSIONS + C_SOURCE_FILES_EXTENSIONS + HEADER_FILES_EXTENSIONS


class CommandsParser:
    '''
    An object for finding and parsing the compile_commands.json file.
    '''
    COMPILE_COMMANDS_FILENAME = 'compile_commands.json'

    # Patterns for get_relevant_args()
    EXCLUDE_FLAGS = {
        r'cc$': 1,
        r'-c$': 1,
        r'-o.+': 1,
        r'-o$': 2,
        # Debug symbols
        r'-g': 1,
        # Optimizations
        r'-O.?$': 1,
        # Linker flags
        r'-(?:[st]|static|shared)$': 1,
        r'-[Lle].+': 1,
        r'-[zLle]$': 2,
        r'-T(?:bss|data|text)?.+': 1,
        r'-T(?:bss|data|text)?$': 2,
        r'--(?:library-directory|for-linker)=': 1,
        r'--(?:library-directory|for-linker)$': 2,
        r'-Wl,': 1,
        r'-X(?:linker)?$': 2,
        r'-r(?:path)?$': 2,
        r'--entry$': 1,
        r'-fuse-ld=': 1,
    }

    # Used to find args for files that are not in the compile commands, like most headers
    __C_CPP_SOURCE_FILES_EXTENSIONS = [re.escape(ext) for ext in ALL_C_CPP_FILES_EXTENSIONS]

    def __init__(self, *, commands_path: AnyStr = None, exclude_flags: Dict[Text, int] = None):
        self.__commands_getter = None
        if commands_path is not None:
            if os.path.isdir(commands_path):
                commands_path = os.path.join(commands_path, CommandsParser.COMPILE_COMMANDS_FILENAME)

            if os.path.isfile(commands_path):
                with open(commands_path) as commands_fd:
                    commands = json.load(commands_fd)

                self.__commands_getter = lambda filename: commands
            else:
                warn(f"Ignoring the provided commands_path. Reason: missing: '{commands_path}' is not a file.",
                     category=MissingCompileCommands, stacklevel=2)

        if not self.__commands_getter:
            self.__commands_getter = CommandsParser.__get_compile_commands

        if exclude_flags is None:
            exclude_flags = CommandsParser.EXCLUDE_FLAGS

        self.exclude = exclude_flags

    @staticmethod
    def _find_compile_commands(start_at: AnyStr = None) -> AnyStr:
        '''
        Find the compile commands json file.

        @param start_at Use this directory as a starting point. Defaults to cwd.
        '''
        if start_at is None:
            start_at = os.getcwd()

        cur_dir = os.path.abspath(start_at)
        while CommandsParser.COMPILE_COMMANDS_FILENAME not in os.listdir(cur_dir):
            prev_dir = cur_dir
            cur_dir = os.path.abspath(os.path.join(cur_dir, os.pardir))
            if cur_dir == prev_dir:
                break
        else:
            return os.path.join(cur_dir, CommandsParser.COMPILE_COMMANDS_FILENAME)

    @staticmethod
    @lru_cache
    def __get_compile_commands(filename: AnyStr) -> CompileCommands:
        commands_filename = CommandsParser._find_compile_commands(os.path.dirname(filename))

        if commands_filename and os.path.isfile(commands_filename):
            with open(commands_filename) as commands_file:
                return json.load(commands_file)
        return []

    @lru_cache
    def _find_in_commands(self, filename: AnyStr) -> CompileCommandsEntry:
        '''
        Find the commands to compile `filename`.
        `None` is returned if no such command is found.

        @param filename The file to look for.
        @param commands A compile_commands.json style dictionary.
        '''
        if isinstance(filename, bytes):
            filename = filename.decode()

        close_cmd = None
        loose_match = re.compile(re.escape(os.path.splitext(filename)[0]) +
                                 rf'(?:{"|".join(CommandsParser.__C_CPP_SOURCE_FILES_EXTENSIONS)})$')

        commands = self.__commands_getter(filename)
        for cmd in commands:
            cmd_file = os.path.abspath(os.path.join(cmd['directory'], cmd['file']))
            if cmd_file == filename:
                return cmd

            if loose_match.search(cmd_file):
                close_cmd = cmd

        return close_cmd

    @staticmethod
    def __filter_by_regex(pattern: Pattern, remove_count: int, args: Iterable[Text]) -> Iterable[Text]:
        assert remove_count >= 1

        removing = 0
        for arg in args:
            if removing > 0:
                removing -= 1
            elif re.match(pattern, arg):
                removing = remove_count - 1
            else:
                yield arg

    def __get_relevant_args(self, entry: CompileCommandsEntry) -> List[Text]:
        '''
        Get a list of relevant compilation flags from `command` field in the compile command.

        @param entry The entire command dictionary.
        '''
        args = shlex.split(entry['command'])

        for pattern, arg_count in self.exclude.items():
            args = CommandsParser.__filter_by_regex(pattern, arg_count, args)

        # Unpack generators
        args = list(args)

        # Remove the file itself
        if args[-1] == os.path.relpath(entry['file'], start=entry['directory']):
            args.pop(-1)

        return args

    def __common_flags(self, commands: CompileCommands) -> List[Text]:
        '''
        Get all flags that are common among for all files.

        @param commands The compile commands.
        '''
        flags = None
        for cmd in commands:
            cmd_flags = set(self.__get_relevant_args(cmd))
            flags = flags & cmd_flags if flags is not None else cmd_flags
        return list(flags)

    @lru_cache
    def get_args(self, filename: AnyStr) -> Tuple[Text, List[Text]]:
        '''
        Get the compilation parameters for `filename`.

        @param filename     The name of the file. Use Clang.STDIN_FILENAME when using a non-file stdin.

        @returns (compilation_directory, args_list)
        '''
        if os.path.isfile(filename):
            filename = os.path.abspath(filename)

            if cmd := self._find_in_commands(filename):
                return cmd['directory'], self.__get_relevant_args(cmd)

        if compile_commands := self.__commands_getter(filename):
            return compile_commands[0]['directory'], self.__common_flags(compile_commands)

        return os.getcwd(), []


class Clang:
    '''
    An object for running clang plugins.
    '''
    STDIN_FILENAME = '-'
    __FLAG_PREFIX = '-Xclang'
    __LOAD_LIB_FLAG = '-load'
    __RUN_PLUGIN_FLAG = '-plugin'  # Run as main command
    __ADD_PLUGIN_FLAG = '-add-plugin'  # Run after main command
    __SYNTAX_ONLY_FLAG = '-fsyntax-only'

    def __init__(self, exec_path: AnyStr = 'clang++-10', *,
                 commands_parser: CommandsParser = None,
                 verbose: bool = False):
        self.verbose = verbose
        self.exec_path = exec_path
        self.__plugins = {}
        self.__compile_commands = commands_parser or CommandsParser()

    def run(self, filename: AnyStr, extra_args: Iterable[Text] = None, clang_args: Iterable[Text] = None, *,
            get_stdout: bool = False, check: bool = False, ignore_cmds: bool = False,
            **kwargs) -> subprocess.CompletedProcess:
        '''
        Run clang on `filename`.

        @param filename     The name of the file. Use Clang.STDIN_FILENAME when using a non-file stdin.
        @param extra_args   Additional args to append to the compile commands' flags.
        @param get_stdout   If `True`, return clang's stdout. Otherwise, return the exit code.
        @param check        If `True` and the exit code was non-zero, raise a PluginError. The PluginError object will
                            have the return code in the returncode attribute, and output & stderr attributes if those
                            streams were captured (stderr is captured whenever the stderr argument is not provided and
                            the verbose attribute is `False`).
        @param ignore_cmds  If `True`, the compiler ignores the compile commands.
        @param kwargs       Additional args for subprocess, `text`, `shell` and `executable` are ignored.

        @returns CompletedProcess   The returned instance will have attributes args, returncode, stdout and stderr.
                                    When stdout and stderr are not captured, and those attributes will be None.
        '''
        if filename != Clang.STDIN_FILENAME:
            assert os.path.isfile(filename)
            filename = os.path.abspath(filename)

        if extra_args is None:
            extra_args = []
        if not isinstance(extra_args, list):
            extra_args = list(extra_args or [])

        if clang_args is None:
            clang_args = []
        clang_args = list(chain(*((Clang.__FLAG_PREFIX, flag) for flag in clang_args)))

        if ignore_cmds:
            run_dir, args = os.getcwd(), []
        else:
            run_dir, args = self.__compile_commands.get_args(filename)

        error_stream = kwargs.pop('stderr', None if self.verbose else subprocess.PIPE)
        output_stream = kwargs.pop('stdout', subprocess.PIPE if get_stdout else None)

        # Ignore some keyword arguments:
        kwargs.pop('executable', None)
        kwargs.pop('shell', None)
        kwargs.pop('text', None)

        with directory(run_dir):
            proc = subprocess.run([self.exec_path, '-x', 'c++'] + clang_args + args + extra_args + [os.path.relpath(filename)],
                                  stderr=error_stream, stdout=output_stream, text=True, check=False, **kwargs)

        if check and proc.returncode != 0:
            if self.verbose:
                print("error: {!r} exited with {}.".format(proc.args[0], proc.returncode), file=sys.stderr)
                print("command: {!r}".format(' '.join(proc.args)), file=sys.stderr)
            raise PluginError(proc)

        return proc

    def check_syntax(self, filename: AnyStr, extra_args: Iterable[Text] = None, **kwargs) -> bool:
        '''
        Check for syntax errors in `filename` using clang's -fsyntax-only.

        @param filename     The name of the file. Use Clang.STDIN_FILENAME when using a non-file stdin.
        @param extra_args   Additional args to append to the compile commands' flags.
        @param kwargs       Additional args for subprocess, `stderr`, `shell` and `executable` are ignored.

        @returns bool
        '''
        return self.run(filename, extra_args=[Clang.__SYNTAX_ONLY_FLAG] + list(extra_args or []), **kwargs).returncode == 0

    def preprocess(self, filename: AnyStr, extra_args: Iterable[Text] = None, trim: bool = True, **kwargs) -> Text:
        '''
        Preprocess `filename`.

        @param filename     The name of the file. Use Clang.STDIN_FILENAME when using a non-file stdin.
        @param extra_args   Additional args to append to the compile commands' flags.
        @param trim         Whether to remove preprocessor markings and trim whitespaces.
        @param kwargs       Additional args for subprocess, `stderr`, `shell` and `executable` are ignored.

        @returns str
        '''
        output = self.run(filename, extra_args=['-E'] + list(extra_args or []),
                          get_stdout=True, check=True, **kwargs).stdout

        if trim:
            # Remove preprocessor markings
            output = re.sub(r'^#.*$', '', output, flags=re.M)

            # Trim whitespace
            output = re.sub(r'\n\s*\n', '\n', output, flags=re.M | re.S)

        return output

    def get_macros(self, filename: AnyStr, extra_args: Iterable[Text] = None, **kwargs) -> Dict[Text, Text]:
        '''
        Extract all macros from `filename`

        @param filename     The name of the file. Use Clang.STDIN_FILENAME when using a non-file stdin.
        @param extra_args   Additional args to append to the compile commands' flags.
        @param kwargs       Additional args for subprocess, `stderr`, `shell` and `executable` are ignored.

        @returns Dict[Text, Text]   The dictionary that maps between the macros' names and their definitions.
        '''
        pp_output = self.preprocess(filename, extra_args=['-dM'] + list(extra_args or []), trim=False, **kwargs)

        if "ignore_cmds" in kwargs:
            kwargs.pop("ignore_cmds")

        macro_names = re.findall(r'^#define (?P<name>\w+)(?!\(.*\))(?: |$)', pp_output, flags=re.M)

        # The preprocessor compressed packs of empty lines, so a magic prefix is used to prevent it
        _MAGIC_PREFIX = ': '  # pylint: disable=invalid-name
        # A pseudo file is generated to contain all defines and the macros whose expanded forms are needed
        macro_dumper = pp_output + '\n'.join(f'{_MAGIC_PREFIX}{name}' for name in macro_names) + '\n'
        macro_definitions = self.preprocess(Clang.STDIN_FILENAME, ['-Wno-macro-redefined'], trim=False,
                                            input=macro_dumper, ignore_cmds=True, **kwargs).split('\n')[:-1]

        return dict(zip(reversed(macro_names), (macro_def[len(_MAGIC_PREFIX):] for macro_def in reversed(macro_definitions))))

    def run_plugin(self, plugin_lib: AnyStr, plugin_name: AnyStr, filename: AnyStr, extra_args: Iterable[Text] = None, *,
                   get_stdout: bool = True, check: bool = False, **kwargs) -> subprocess.CompletedProcess:
        '''
        Run clang with the specified plugin on `filename`.

        @param plugin_lib   The shared object file that contains the plugin.
        @param plugin_name  The name of the plugin.
        @param filename     The name of the file. Use Clang.STDIN_FILENAME when using a non-file stdin.
        @param extra_args   Additional args to append to the compile commands' flags.
        @param get_stdout   If `True`, return clang's stdout. Otherwise, return the exit code.
        @param check        If `True` and the exit code was non-zero, raise a PluginError. The PluginError object will
                            have the return code in the returncode attribute, and output & stderr attributes if those
                            streams were captured (stderr is captured whenever the stderr argument is not provided and
                            the verbose attribute is `False`).
        @param kwargs Additional args for subprocess, `stderr`, `shell` and `executable` are ignored.

        @returns CompletedProcess   The returned instance will have attributes args, returncode, stdout and stderr.
                                    When stdout and stderr are not captured, and those attributes will be None.
        '''
        plugin_lib = os.path.abspath(plugin_lib)

        return self.run(filename,
                        extra_args=[Clang.__SYNTAX_ONLY_FLAG] + list(extra_args or []),
                        clang_args=[Clang.__LOAD_LIB_FLAG, plugin_lib, Clang.__RUN_PLUGIN_FLAG, plugin_name],
                        get_stdout=get_stdout,
                        check=check,
                        **kwargs)

    def register_plugin(self, plugin_lib: AnyStr, plugin_name: AnyStr):
        '''
        Register a plugin to run later.

        @param plugin_lib   The shared object file that contains the plugin.
        @param plugin_name  The name of the plugin.
        '''
        self.__plugins[plugin_name] = plugin_lib

    def run_plugins(self, filename: AnyStr, extra_args: Iterable[Text] = None, *,
                    get_stdout: bool = True, check: bool = False, **kwargs) -> subprocess.CompletedProcess:
        '''
        Run clang with the registered plugins on `filename`.

        @param filename     The name of the file. Use Clang.STDIN_FILENAME when using a non-file stdin.
        @param extra_args   Additional args to append to the compile commands' flags.
        @param get_stdout   If `True`, return clang's stdout. Otherwise, return the exit code.
        @param check        If `True` and the exit code was non-zero, raise a PluginError. The PluginError object will
                            have the return code in the returncode attribute, and output & stderr attributes if those
                            streams were captured (stderr is captured whenever the stderr argument is not provided and
                            the verbose attribute is `False`).
        @param kwargs Additional args for subprocess, `stderr`, `shell` and `executable` are ignored.

        @returns CompletedProcess   The returned instance will have attributes args, returncode, stdout and stderr.
                                    When stdout and stderr are not captured, and those attributes will be None.
        '''
        if extra_args is None:
            extra_args = []

        plugin_libs = list(chain(*{(Clang.__LOAD_LIB_FLAG, os.path.abspath(plugin_lib))
                                   for plugin_lib in self.__plugins.values()}))
        plugin_names = list(chain(*((Clang.__ADD_PLUGIN_FLAG, plugin) for plugin in self.__plugins)))

        return self.run(filename,
                        extra_args=[Clang.__SYNTAX_ONLY_FLAG] + list(extra_args or []),
                        clang_args=plugin_libs + plugin_names,
                        get_stdout=get_stdout,
                        check=check,
                        **kwargs)
