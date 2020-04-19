'''
Implements base parsers for parsing compiler plugin output.
'''
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from re import compile as _compile_re
from typing import Any, List, Optional, Pattern, Text, Tuple

from .cpp.scope import Scope


@dataclass(frozen=True)
class Context:
    '''
    Represents an input line's context.

    Members:
        - lines -- A list of all lines in the input.
        - current_line -- The index of the current line.
        - global_scope -- The global scope to plat parsed values in.
    '''
    lines: List[Text]
    current_line: int
    global_scope: Scope


class ParsingError(Exception):
    '''
    Raised to indicate parsing errors.
    '''

    def __init__(self, line: Text, context: Optional[Context] = None):
        super().__init__(line, context)

        self.line = line
        self.context = context

    def __str__(self):
        if self.context:
            return f"Error parsing line #{self.context.current_line + 1}: {self.line!r}"
        return f"Error parsing line: {self.line!r}"


class ParserBase(metaclass=ABCMeta):
    '''
    Base class for parsers.
    '''

    @abstractmethod
    def parse_line(self, line: Text, context: Context) -> bool:
        '''
        Parses the current line. Adding parsed objects to the context's scope

        @param line     The current line's content.
        @param context  The context.

        @returns Whether the line was successfully parsed.
        '''

    def parse_single_line(self, line: Text) -> Tuple[Text, Any]:
        '''
        Parses a single line without context.

        @param line The current line's content.

        @returns (str, object)  The parsed object and it's name (name is first).
        '''
        # A `dict` instead of a `Scope` to make 'my_project::size = 5' return as ('my_project::size', 5)
        single_object_scope = {}
        if not self.parse_line(line, Context(lines=[line], current_line=0, global_scope=single_object_scope)):
            raise ParsingError(line)

        assert len(single_object_scope) == 1

        return tuple(single_object_scope.items())[0]

    def parse(self, data: Text, initial_scope: Optional[Scope] = None, strict: bool = True) -> Scope:
        '''
        Parses the entire string into a scope.

        @param data             The string to parse.
        @param initial_scope    The initial scope to use, defaults to a new empty scope.
        @param strict           If ``True``, raise an error on invalid lines. Otherwise, ignore invalid lines.

        @returns The created scope object (or ``initial_scope`` if it was provided).
        '''
        if initial_scope is None:
            initial_scope = Scope()

        lines = data.split('\n')
        for i, line in enumerate(lines):
            context = Context(lines=lines, current_line=i, global_scope=initial_scope)
            if not self.parse_line(line, context) and strict:
                raise ParsingError(line, context)

        return initial_scope


class _EmptyParser(ParserBase):
    def __init__(self, pattern: Pattern):
        self._re = _compile_re(pattern)

    def parse_line(self, line: Text, context: Context) -> bool:
        return self._re.match(line) is not None


_NONE_PARSER = _EmptyParser(r'')
_BLANK_LINES_PARSER = _EmptyParser(r'^\s*$')


class Parser(ParserBase):
    '''
    TODO: docs
    '''

    def __init__(self, *sub_parsers: ParserBase, strict: bool = True, ignore_empty: bool = True):
        if not strict:
            self._parsers = (*sub_parsers, _NONE_PARSER)
        elif ignore_empty:
            self._parsers = (*sub_parsers, _BLANK_LINES_PARSER)
        else:
            self._parsers = sub_parsers

    def parse_line(self, line: Text, context: Context) -> bool:
        # Using list to make the any() not lazy-evaluated, calling all parsers
        return any([parser.parse_line(line, context) for parser in self._parsers])
