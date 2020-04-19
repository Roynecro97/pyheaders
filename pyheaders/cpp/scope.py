'''
Represents a C++ scope (namespace, class, enum class, ...).
'''

from collections import OrderedDict
from typing import Any, Text, Optional, Tuple


class Scope(OrderedDict):
    '''
    Represents a C++ scope (namespace, class, enum class, ...).
    '''
    SEP: Text = '::'

    @staticmethod
    def _extract_first_name(name: Text) -> Tuple[Text, Optional[Text]]:
        first_sep_index = name.find(Scope.SEP)
        if first_sep_index >= 0:
            return name[:first_sep_index], name[first_sep_index + len(Scope.SEP):]
        else:
            return name, None

    def __getitem__(self, name: Text):
        if not isinstance(name, str):
            raise TypeError("name must be a str.")

        name, inner = Scope._extract_first_name(name)

        if inner is not None:
            return super().__getitem__(name)[inner]
        else:
            return super().__getitem__(name)

    def __setitem__(self, name: Text, value: Any):
        if not isinstance(name, str):
            raise TypeError("name must be a str.")

        name, inner = Scope._extract_first_name(name)
        if inner is not None:
            if name not in self:
                super().__setitem__(name, Scope())
            self[name][inner] = value
        else:
            super().__setitem__(name, value)

    def get(self, key: Text, default: Optional[Any] = None, /):
        if key in self:
            return self[key]
        return default

    def __contains__(self, name: Text):
        if not isinstance(name, str):
            raise TypeError("name must be a str.")

        name, inner = Scope._extract_first_name(name)
        if inner is not None:
            return super().__contains__(name) and inner in self[name]
        else:
            return super().__contains__(name)


def split(name: Text) -> Tuple[Optional[Text], Text]:
    first_sep_index = name.rfind(Scope.SEP)
    if first_sep_index >= 0:
        return name[:first_sep_index], name[first_sep_index + len(Scope.SEP):]
    else:
        return None, name
