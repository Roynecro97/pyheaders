'''
Represents a C++ scope (namespace, class, enum class, ...).
'''

from copy import deepcopy
from collections import OrderedDict


class Scope:
    '''
    Represents a C++ scope (namespace, class, enum class, ...).
    '''
    SEP = '::'

    def __init__(self, members=None):
        # TODO: validate types
        if members is None:
            members = OrderedDict()

        self._members = deepcopy(members)

    @staticmethod
    def _extract_first_name(name):
        first_sep_index = name.find(Scope.SEP)
        if first_sep_index >= 0:
            return name[:first_sep_index], name[first_sep_index + len(Scope.SEP):]
        else:
            return name, None

    def __getitem__(self, name):
        if not isinstance(name, str):
            raise TypeError("name must be a str.")

        name, inner = Scope._extract_first_name(name)

        if inner is not None:
            return self._members[name][inner]
        else:
            return self._members[name]

    def __setitem__(self, name, value):
        if not isinstance(name, str):
            raise TypeError("name must be a str.")

        name, inner = Scope._extract_first_name(name)
        if inner is not None:
            if name not in self._members:
                self._members[name] = Scope()
            self._members[name][inner] = value
        else:
            self._members[name] = value

    def __contains__(self, name):
        if not isinstance(name, str):
            raise TypeError("name must be a str.")

        name, inner = Scope._extract_first_name(name)
        if inner is not None:
            return name in self._members and inner in self._members[name]
        else:
            return name in self._members

    def __iter__(self):
        return iter(self._members)

    def __len__(self):
        return len(self._members)

    def keys(self):
        return self._members.keys()

    def values(self):
        return self._members.values()

    def items(self):
        return self._members.items()

    def __str__(self):
        return '[{}]'.format(', '.join('{!r}: {!r}'.format(name, value) for name, value in self.items()))

    def __repr__(self):
        return 'Scope({!r})'.format(self._members)


def split(name):
    first_sep_index = name.rfind(Scope.SEP)
    if first_sep_index >= 0:
        return name[:first_sep_index], name[first_sep_index + len(Scope.SEP):]
    else:
        return None, name
