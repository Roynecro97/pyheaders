'''
Represents a C++ enum.
'''
from collections import OrderedDict


class Enum:
    '''
    Represents a C++ enum.
    '''

    def __init__(self, name, items=None):
        # TODO: validate types
        if items is None:
            items = []
        self.name = name
        self._items = OrderedDict(items)

    def __getitem__(self, name):
        if isinstance(name, str):
            return self._items[name]
        elif isinstance(name, int):
            value = name
            if name not in self._items.values():
                # TODO: improve
                raise KeyError
            return [name for name, val in self._items.items() if val == value][0]
        else:
            raise TypeError("Parameter must be a str or an int.")

    def __setitem__(self, name, value):
        if not isinstance(name, str):
            raise TypeError("name must be a str.")
        if not isinstance(value, int):
            raise TypeError("value must be an int.")
        self._items[name] = value

    def __contains__(self, item):
        if not isinstance(item, (str, int)):
            raise TypeError("item must be a str or an int.")
        return item in self._items or item in self._items.values()

    def __iter__(self):
        return iter(self._items)

    def __len__(self):
        return len(self._items)

    def keys(self):
        return self._items.keys()

    def values(self):
        return self._items.values()

    def items(self):
        return self._items.items()

    def __str__(self):
        return 'enum {}'.format(self.name)

    def __repr__(self):
        return 'Enum({!r}, [{}])'.format(self.name, ', '.join('({!r}, {!r})'.format(item, value) for item, value in self.items()))
