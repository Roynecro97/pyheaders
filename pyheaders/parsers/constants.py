'''
Parser for the ConstantsDumper variables.
'''

import re

from typing import Text

from ..parser import Context, ParserBase


class ConstantsParser(ParserBase):
    '''
    Parses the constants outputted by the ConstantDumper clang plugin.
    '''
    VALUE_MATCHER = re.compile(r'^\s*(?P<name>.+?)\s*=\s*(?P<value>.+?)\s*,?\s*$')

    def parse_line(self, line: Text, context: Context) -> bool:
        if value_match := ConstantsParser.VALUE_MATCHER.match(line):
            name = value_match.group('name')
            value = int(value_match.group('value'))
            context.global_scope[name] = value

        return bool(value_match)
