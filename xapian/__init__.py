# -*- coding: UTF-8 -*-
# Copyright (C) 2007 Henry Obein <henry@itaapy.com>
# Copyright (C) 2007 Juan David Ibáñez Palomar <jdavid@itaapy.com>
# Copyright (C) 2008 David Versmisse <david.versmisse@itaapy.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Import from itools
from base import CatalogAware
from catalog import Catalog, make_catalog
from fields import (BaseField, TextField, KeywordField, IntegerField,
                    BoolField, register_field, get_field)
from queries import (EqQuery, RangeQuery, PhraseQuery, AndQuery, OrQuery,
                     NotQuery)

__all__ = [
    'make_catalog',
    'Catalog',
    'CatalogAware',
    # Fields
    'BaseField',
    'TextField',
    'KeywordField',
    'IntegerField',
    'BoolField',
    'register_field',
    'get_field',
    # Queries
    'EqQuery',
    'RangeQuery',
    'PhraseQuery',
    'AndQuery',
    'OrQuery',
    'NotQuery']
