'''
C++ headers parsing library

This module is a C++ header/source parsing library that allows getting constants that are known at compile-time
into Python code.
'''
import os

from typing import AnyStr as _Path, IO as _IO, Iterable as _Iterable, Text as _Text

from . import compiler
from . import cpp
from . import parser
from . import parsers
from . import utils


def _load_file(filename: _Path, /, extra_args: _Iterable[_Text] = None, *, verbose: bool = False,
               initial_scope: cpp.Scope = None, **run_plugin_kwargs) -> cpp.Scope:
    assert os.path.isfile(filename) or filename == compiler.Clang.STDIN_FILENAME

    clang = compiler.Clang(verbose=verbose)

    clang.register_plugin(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'plugins', 'ConstantsDumper.so'),
                          'ConstantsDumper')

    consts_txt = clang.run_plugins(filename, extra_args, check=True, **run_plugin_kwargs).stdout

    consts_parser = parser.Parser(parsers.enums.EnumsParser(), parsers.constants.ConstantsParser())
    return consts_parser.parse(consts_txt, initial_scope=initial_scope, strict=True)


def load_path(path: _Path, /, extra_args: _Iterable[_Text] = None, *, verbose: bool = False, **run_plugin_kwargs) -> cpp.Scope:
    '''
    Load all constants from ``path`` (a ``str`` or ``bytes`` instance containing a
    path to a file or a directory containing C++ code) to a Python object.

    @param path         The path of the file or directory to load. If a directory is
                        given, all files whose extension is recognized as a C/C++ source
                        code extension are loaded.
    @param extra_args   Additional compilation arguments on top of the compile commands.
    @param verbose      If ``True`` is provided, don't suppress compiler errors.
    @param run_plugin_kwargs Additional args for run_plugin().

    @returns Scope
    '''
    if os.path.isfile(path):
        return _load_file(path, extra_args=extra_args, verbose=verbose, **run_plugin_kwargs)

    if os.path.isdir(path):
        global_scope = cpp.Scope()

        source_files = (os.path.join(dirpath, filename) for dirpath, _, files in os.walk(path) for filename in files
                        if os.path.splitext(filename)[-1] in compiler.C_CPP_SOURCE_FILES_EXTENSIONS)
        for filename in source_files:
            filename = os.path.join(path, filename)

            _load_file(filename, extra_args=extra_args,
                       verbose=verbose,
                       initial_scope=global_scope,
                       **run_plugin_kwargs)

        return global_scope

    raise ValueError('path is neither a file nor a directory.')


def loads(code: _Text, /, extra_args: _Iterable[_Text] = None, *, verbose: bool = False, **run_plugin_kwargs) -> cpp.Scope:
    '''
    Load all constants from ``code`` (a ``str`` instance containing C++ code) to a
    Python object.

    @param code         The code to load.
    @param extra_args   Additional compilation arguments on top of the compile commands.
    @param verbose      If ``True`` is provided, don't suppress compiler errors.
    @param run_plugin_kwargs Additional args for run_plugin().

    @returns Scope
    '''
    return _load_file(compiler.Clang.STDIN_FILENAME, extra_args=extra_args, verbose=verbose, input=code, **run_plugin_kwargs)


def load(source_file: _IO, /, extra_args: _Iterable[_Text] = None, *, verbose: bool = False, **run_plugin_kwargs) -> cpp.Scope:
    '''
    Load all constants from ``source_file`` (a ``.read()``-supporting file-like object
    containing C++ code) to a Python object.

    @param source_file  The file to load.
    @param extra_args   Additional compilation arguments on top of the compile commands.
    @param verbose      If ``True`` is provided, don't suppress compiler errors.
    @param run_plugin_kwargs Additional args for run_plugin().

    @returns Scope
    '''
    return loads(source_file.read(), extra_args=extra_args, verbose=verbose, **run_plugin_kwargs)
