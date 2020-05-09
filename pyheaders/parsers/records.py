'''
Parser for the TypesDumper classes / structs.
'''

import re

from typing import Text

from ..cpp import Record
from ..parser import Context, ParserBase


class RecordsParser(ParserBase):
    '''
    Parses the classes and structs outputted by the TypesDumper clang plugin.
    '''
    RECORD_MATCHER = re.compile(r'^(?P<name>.+?)\{(?P<fields>.*)\}$')

    def parse_line(self, line: Text, context: Context) -> bool:
        if type_match := RecordsParser.RECORD_MATCHER.match(line):
            name = type_match.group('name')
            fields = type_match.group('fields')
            context.global_scope[name] = Record(name, fields, context.global_scope.get(name, []))

        return bool(type_match)
