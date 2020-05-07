'''
Parser for the ConstantsDumper enums.
'''

import re

from typing import Any, Dict, Optional, Tuple, Text

from .constants import ConstantsParser

from ..cpp import Enum
from ..cpp import split as split_scope
from ..parser import Context, ParserBase


class EnumsParser(ParserBase):
    '''
    Parses the enums outputted by the ConstantsDumper clang plugin.
    '''
    ENUM_START_MATCHER = re.compile(r'^\s*enum\s+(?P<name>.+?)\s*{\s*$')
    ENUM_END_MATCHER = re.compile(r'\s*}\s*')
    __ANONYMOUS_MATCHER = re.compile(r'\W+anonymous\W+', flags=re.I)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__anonymous_in_scope: Dict[Text, int]
        self.__current_enum: Optional[Enum]

        # Only `int`s are allowed in enums so a default parser is OK.
        self.__values_parser = ConstantsParser()

        self.reset()

    def reset(self):
        '''
        Reset internal counters.
        '''
        self.__anonymous_in_scope = {}
        self.__current_enum = None

    @staticmethod
    def __is_anonymous_name(enum_name: Text) -> bool:
        return EnumsParser.__ANONYMOUS_MATCHER.match(enum_name)

    def parse_line(self, line: Text, context: Context) -> bool:
        if enum_match := EnumsParser.ENUM_START_MATCHER.match(line):
            if self.__current_enum is not None:
                return False

            name = enum_match.group('name')
            enum_scope, enum_name = split_scope(name)

            if EnumsParser.__is_anonymous_name(enum_name):
                anonymous_num = self.__anonymous_in_scope.get(enum_scope, 0)
                name += f'`{anonymous_num}'
                self.__anonymous_in_scope[enum_scope] = anonymous_num + 1

            self.__current_enum = Enum(enum_name)
            context.global_scope[name] = self.__current_enum

            return True
        if self.__current_enum is not None:
            # Inside an enum, collect values using the ConstantsParser
            if EnumsParser.ENUM_END_MATCHER.match(line):
                self.__current_enum = None
            else:
                full_name, value = self.__values_parser.parse_single_line(line)
                *_, name = split_scope(full_name)
                self.__current_enum[name] = value

            return True

        return False

    def parse_single_line(self, line: Text) -> Tuple[Text, Any]:
        raise NotImplementedError("Single line parsing is not supported by EnumsParser.")
