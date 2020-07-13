'''
Represents a C++ scope (namespace, class, enum class, ...).
'''

import re

from collections import OrderedDict
from typing import Any, Optional, Pattern, Text, Tuple

from .types import OPERATOR_KW as _OP_KW, OPERATOR_PROBLEMATIC_CHARS as _PROBLEMATIC_CHARS
from .types import TEMPLATE_START, TEMPLATE_END, PARENS_START, PARENS_END


class Scope(OrderedDict):
    '''
    Represents a C++ scope (namespace, class, enum class, ...).
    '''
    SEP: Text = '::'
    # Equivalent to: \([^:()]*\banonymous\b[^:()]*\)::
    ANONYMOUS_NAMESPACE: Pattern = rf'\([^{SEP}()]*\banonymous\b[^{SEP}()]*\){SEP}'

    _PLACEHOLDER = '@'
    assert _PLACEHOLDER not in SEP

    @staticmethod
    def _safe_name(name: Text) -> Text:
        '''
        Prevent detection of scope separators inside templates or parentheses.
        '''
        def match_bracket(parenthesis, template):
            # The second part of the template-related condition is to not catch `r'operator[<>]*'`.
            # This is not needed for parentheses because the only operator with them is 'operator()',
            # so we open and close and it's OK.
            return name[i] == parenthesis or \
                (name[i] == template and not name[:i].rstrip(_PROBLEMATIC_CHARS).endswith(_OP_KW))

        safe_name = ''
        bracket_level = 0
        i = 0
        while i < len(name):
            if match_bracket(PARENS_START, TEMPLATE_START):
                bracket_level += 1
            elif match_bracket(PARENS_END, TEMPLATE_END):
                bracket_level -= 1

            if bracket_level and name.find(Scope.SEP, i, i + len(Scope.SEP)) == i:
                safe_name += Scope._PLACEHOLDER * len(Scope.SEP)
                i += len(Scope.SEP)
            else:
                safe_name += name[i]
                i += 1

        return safe_name

    @staticmethod
    def _extract_first_name(name: Text) -> Tuple[Text, Optional[Text]]:
        name = normalize(name)

        first_sep_index = Scope._safe_name(name).find(Scope.SEP)
        if first_sep_index >= 0:
            return name[:first_sep_index], name[first_sep_index + len(Scope.SEP):]
        return name, None

    def __getitem__(self, name: Text):
        if not isinstance(name, str):
            raise TypeError("name must be a str.")

        name, inner = Scope._extract_first_name(name)

        if inner is not None:
            return super().__getitem__(name)[inner]
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
        return super().__contains__(name)

    def isempty(self) -> bool:
        '''
        S.isempty() -> bool.  Check if there are any items in S that are not a Scope.
        '''
        return all(isinstance(item, Scope) and item.isempty() for item in self.values())


def normalize(name: Text) -> Text:
    '''
    Normalize name by removing leading namespace separators and anonymous namespaces.
    '''
    if name.startswith(Scope.SEP):
        name = name[len(Scope.SEP):]

    return re.sub(Scope.ANONYMOUS_NAMESPACE, '', name)


def split(name: Text) -> Tuple[Optional[Text], Text]:
    '''
    Separate the last name component from the "scope" part.
    '''
    # pylint: disable=protected-access
    first_sep_index = Scope._safe_name(name).rfind(Scope.SEP)
    if first_sep_index >= 0:
        return name[:first_sep_index], name[first_sep_index + len(Scope.SEP):]
    return None, name
