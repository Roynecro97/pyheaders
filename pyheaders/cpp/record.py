'''
Represents a C++ record (class, struct).
'''

from collections import namedtuple
from keyword import iskeyword as _iskeyword
from typing import Any, Iterable, List, Text, Tuple, Union

from .scope import Scope, split


class Record(Scope):
    '''
    Represents a C++ class or struct.
    '''
    @staticmethod
    def _safe_field_names(field_names: Union[Text, Iterable[Text]]) -> List[Text]:
        '''
        Rename problematic field names to not be problematic.
        Based on `namedtuple(..., rename=True)`.
        '''
        if isinstance(field_names, str):
            field_names = field_names.replace(',', ' ').split()

        safe_names = []
        seen = {}
        for index, name in reversed(tuple(enumerate(field_names))):
            if not name.isidentifier() or _iskeyword(name):
                safe_names.insert(0, f'_{index}')
            elif name in seen:
                new_name = f'{name}_{seen[name]}'
                safe_names.insert(0, new_name)
                seen[name] += 1
                seen[new_name] = 1
            else:
                if name.startswith('_'):
                    name = name.lstrip('_')
                safe_names.insert(0, name)
                seen[name] = 1
        return safe_names

    def __init__(self, name: Text, field_names: Union[Text, Iterable[Text]], base_scope: Iterable[Tuple[Text, Any]] = None):
        super().__init__(base_scope or [])

        self.__name = name
        self.__fields = tuple(Record._safe_field_names(field_names))
        self.__type = namedtuple(split(self.__name)[-1], self.__fields)

    @property
    def name(self):
        '''
        Gets the name of the class / struct.
        '''
        return self.__name

    @property
    def fields(self):
        '''
        Gets the names of the fields in the class / struct.
        '''
        return self.__fields

    def __call__(self, *args: Any):
        return self.__type(*args)

    def __repr__(self):
        scope_repr = ''
        if self:
            scope_repr = f', Scope{super().__repr__()[len(type(self).__name__):]}'
        return f'{type(self).__name__}({self.name!r}, *{self.__fields!r}{scope_repr})'
