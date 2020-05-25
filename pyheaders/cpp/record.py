'''
Represents a C++ record (class, struct).
'''

from collections import namedtuple
from keyword import iskeyword
from typing import Any, Iterable, List, Text, Tuple, Union

from .scope import Scope, split, normalize
from .types import remove_template


class Record(Scope):
    '''
    Represents a C++ class or struct.
    '''
    _COLLAPSE_SHORT_RECORDS = True

    @staticmethod
    def collapse_short_records(collapse: bool = True):
        '''
        Control whether records with a single field should be collapsed.
        '''
        Record._COLLAPSE_SHORT_RECORDS = bool(collapse)

    @staticmethod
    def _identity(obj):
        return obj

    @staticmethod
    def _safe_field_names(field_names: Union[Text, Iterable[Text]]) -> List[Text]:
        '''
        Rename problematic field names to not be problematic.
        Based on `namedtuple(..., rename=True)`.
        '''
        if isinstance(field_names, str):
            field_names = field_names.replace(',', ' ').split()

        safe_names = []
        seen = set()
        for name in reversed(tuple(field_names)):
            if name in seen:
                name = f'_{name}'
            safe_names.insert(0, name)
            seen.add(name)
        return safe_names

    def __init__(self, name: Text, field_names: Union[Text, Iterable[Text]], base_scope: Iterable[Tuple[Text, Any]] = None):
        super().__init__(base_scope or [])

        self.__name = normalize(name)
        self.__fields = tuple(Record._safe_field_names(field_names))

        if len(self.__fields) == 1 and Record._COLLAPSE_SHORT_RECORDS:
            self.__type = Record._identity
        else:
            module, name = split(remove_template(self.__name))
            if not module:
                module = ''
            if iskeyword(name):
                name = f'_{name}'
            self.__type = namedtuple(name, self.__fields, module=module.replace(Scope.SEP, '.'), rename=True)

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
        return f'{type(self).__name__}({self.name!r}, {self.__fields!r}{scope_repr})'
