'''
C++ headers parsing library

This module is a C++ header/source parsing library that allows getting constants that are known at compile-time
into Python code.
'''
import os

from typing import AnyStr as _Path, Dict as _Dict, IO as _IO, Iterable as _Iterable, Text as _Text, Tuple as _Tuple
from dataclasses import dataclass as _dataclass, field as _field

from . import compiler, cpp, parser, parsers, utils

@_dataclass
class SrcData:
    '''
    dataclass used to store the returned values from pyheaders' API.
    '''
    scope: cpp.Scope = _field(default_factory=cpp.Scope)
    macros: _Dict[_Text, _Text] = _field(default_factory=dict)

    def update(self, other):
        '''
        Updates its data with the data of another SrcData object.
        '''
        self.scope.update(other.scope)
        self.macros.update(other.macros)


def _load_file(filename: _Path, /, extra_args: _Iterable[_Text] = None, *, verbose: bool = False,
               initial_scope: cpp.Scope = None, exec_path: _Path = None,
               commands_parser: compiler.CommandsParser = None, **run_plugin_kwargs) -> SrcData:
    assert os.path.isfile(filename) or filename == compiler.Clang.STDIN_FILENAME

    if exec_path:
        clang = compiler.Clang(exec_path, commands_parser=commands_parser, verbose=verbose)
    else:
        clang = compiler.Clang(commands_parser=commands_parser, verbose=verbose)

    plugins_lib = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'plugins', 'ConstantsDumper.so')
    clang.register_plugin(plugins_lib, 'TypesDumper')
    clang.register_plugin(plugins_lib, 'ConstantsDumper')

    consts_txt = clang.run_plugins(filename, extra_args, check=True, **run_plugin_kwargs).stdout

    consts_parser = parser.Parser(
        parsers.RecordsParser(),
        parsers.EnumsParser(),
        parsers.ConstantsParser(),
        parsers.LiteralsParser(),
    )

    return SrcData(consts_parser.parse(consts_txt, initial_scope=initial_scope, strict=True),
                   clang.get_macros(filename, extra_args, **run_plugin_kwargs))


def load_path(path: _Path, /, extra_args: _Iterable[_Text] = None, *, verbose: bool = False,
              initial_scope: cpp.Scope = None, clang_path: _Path = None,
              commands_parser: compiler.CommandsParser = None, **run_plugin_kwargs) -> SrcData:
    '''
    Load all constants from ``path`` (a ``str`` or ``bytes`` instance containing a
    path to a file or a directory containing C++ code) to a Python object.

    @param path         The path of the file or directory to load. If a directory is
                        given, all files whose extension is recognized as a C/C++ source
                        code extension are loaded.
    @param extra_args   Additional compilation arguments on top of the compile commands.
    @param verbose      If ``True`` is provided, don't suppress compiler errors.
    @param initial_scope The initial scope to use, defaults to a new empty scope.
    @param clang_path   The full path of the clang executable.
    @param commands_parser The CommandsParser object the compiler should use.
    @param run_plugin_kwargs Additional args for run_plugin().

    @returns Scope
    '''
    if os.path.isfile(path):
        return _load_file(path, extra_args=extra_args, verbose=verbose, initial_scope=initial_scope, **run_plugin_kwargs)

    if os.path.isdir(path):
        returned_data = SrcData()
        if initial_scope is not None:
            returned_data.scope = initial_scope

        source_files = (os.path.join(dirpath, filename) for dirpath, _, files in os.walk(path) for filename in files
                        if os.path.splitext(filename)[-1] in compiler.C_CPP_SOURCE_FILES_EXTENSIONS)
        for filename in source_files:
            filename = os.path.join(path, filename)

            returned_data.update(_load_file(filename, extra_args=extra_args, verbose=verbose,
                                            initial_scope=returned_data.scope, exec_path=clang_path,
                                            commands_parser=commands_parser, **run_plugin_kwargs))

        return returned_data

    raise ValueError('path is neither a file nor a directory.')


def loads(code: _Text, /, extra_args: _Iterable[_Text] = None, *, verbose: bool = False,
          initial_scope: cpp.Scope = None, clang_path: _Path = None,
          commands_parser: compiler.CommandsParser = None, **run_plugin_kwargs) -> SrcData:
    '''
    Load all constants from ``code`` (a ``str`` instance containing C++ code) to a
    Python object.

    @param code         The code to load.
    @param extra_args   Additional compilation arguments on top of the compile commands.
    @param verbose      If ``True`` is provided, don't suppress compiler errors.
    @param initial_scope The initial scope to use, defaults to a new empty scope.
    @param clang_path   The full path of the clang executable.
    @param commands_parser The CommandsParser object the compiler should use.
    @param run_plugin_kwargs Additional args for run_plugin().

    @returns Scope
    '''
    return _load_file(compiler.Clang.STDIN_FILENAME, extra_args=extra_args, verbose=verbose,
                      initial_scope=initial_scope, exec_path=clang_path,
                      commands_parser=commands_parser, input=code, **run_plugin_kwargs)


def load(source_file: _IO, /, extra_args: _Iterable[_Text] = None, *, verbose: bool = False,
         initial_scope: cpp.Scope = None, clang_path: _Path = None,
         commands_parser: compiler.CommandsParser = None, **run_plugin_kwargs) -> cpp.Scope:
    '''
    Load all constants from ``source_file`` (a ``.read()``-supporting file-like object
    containing C++ code) to a Python object.

    @param source_file  The file to load.
    @param extra_args   Additional compilation arguments on top of the compile commands.
    @param verbose      If ``True`` is provided, don't suppress compiler errors.
    @param initial_scope The initial scope to use, defaults to a new empty scope.
    @param clang_path   The full path of the clang executable.
    @param commands_parser The CommandsParser object the compiler should use.
    @param run_plugin_kwargs Additional args for run_plugin().

    @returns Scope
    '''
    return loads(source_file.read(), extra_args=extra_args, verbose=verbose, initial_scope=initial_scope,
                 clang_path=clang_path, commands_parser=commands_parser, **run_plugin_kwargs)
