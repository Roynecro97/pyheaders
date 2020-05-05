'''
Represents a C++ enum.
'''
from collections import OrderedDict
from typing import Any, Optional, Text, Union


class Enum(OrderedDict):
    '''
    Represents a C++ enum.
    '''

    def __init__(self, name, items=None):
        super().__init__(items or [])
        self.name = name

    def __getitem__(self, name: Union[Text, Any]) -> Union[Any, Text]:
        if name in self.keys():
            return super().__getitem__(name)

        for key, value in self.items():
            if name == value:
                return key

        raise KeyError(name)

    def __setitem__(self, name: Text, value: Any):
        if not isinstance(name, str):
            raise TypeError("name must be a str.")

        if not name.isidentifier():
            raise ValueError("name must be a valid identifier.")

        super().__setitem__(name, value)

    def get(self, key: Text, default: Optional[Any] = None, /):
        if key in self:
            return self[key]
        return default

    def __contains__(self, name: Text):
        return name in self.keys() or name in self.values()

    def __str__(self):
        return 'enum {}'.format(self.name)

    def __repr__(self):
        return 'Enum({!r}, [{}])'.format(self.name, ', '.join('({!r}, {!r})'.format(item, value) for item, value in self.items()))
