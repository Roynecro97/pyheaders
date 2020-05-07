'''
Parser for the ConstantsDumper magic string literals.
'''

import re

from typing import Dict, Optional, Text

from .constants import ConstantsParser
from ..parser import Context, ParserBase
from ..cpp import split as split_scope
from ..cpp.types import parse_value


class LiteralsParser(ParserBase):
    '''
    Parses the magic string literals outputted by the ConstantsDumper clang plugin.
    '''
    LITERAL_MATCHER = re.compile(r'^\s*#\s*literal\s+(?P<constant>.*)$')
    _LITERAL_UNQUALIFIED_NAME = '(literal)'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__literals_in_scope: Dict[Text, int]
        self.reset()

    def reset(self):
        '''
        Reset internal counters.
        '''
        self.__literals_in_scope = {}

    @staticmethod
    def _get_name_and_value(constant, scope):
        if value_match := ConstantsParser.VALUE_MATCHER.match(constant):
            name = value_match.group('name')
            value = parse_value(value_match.group('value'), scope)
            return name, value
        return None

    def parse_line(self, line: Text, context: Context) -> bool:
        value_match: Optional[re.Match]
        if value_match := LiteralsParser.LITERAL_MATCHER.match(line):
            parsed_constant = LiteralsParser._get_name_and_value(value_match.group('constant'), context.global_scope)
            if not parsed_constant:
                return False

            name, value = parsed_constant
            if not name.endswith(LiteralsParser._LITERAL_UNQUALIFIED_NAME):
                return False

            scope_name = split_scope(name)[0] or ''

            num = self.__literals_in_scope.get(scope_name, 0)
            name += f'`{num}'
            self.__literals_in_scope[scope_name] = num + 1

            context.global_scope[name] = value

        return bool(value_match)
