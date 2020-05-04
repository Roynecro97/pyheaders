'''
Parser for the ConstantsDumper variables.
'''

import re

from typing import Optional, Text

from ..parser import Context, ParserBase


class ConstantsParser(ParserBase):
    '''
    Parses the constants outputted by the ConstantDumper clang plugin.
    '''
    VALUE_MATCHER = re.compile(r'^\s*(?P<name>.+?)\s*=\s*(?P<value>.+?)\s*,?\s*$')

    def parse_line(self, line: Text, context: Context) -> bool:
        value_match: Optional[re.Match]
        if value_match := ConstantsParser.VALUE_MATCHER.match(line):
            name = value_match.group('name')
            value = value_match.group('value')
            if re.match(r'-?\d+$', value):
                value = int(value)
            context.global_scope[name] = value

        return bool(value_match)
