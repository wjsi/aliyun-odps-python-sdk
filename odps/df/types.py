#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright 1999-2022 Alibaba Group Holding Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
from collections import OrderedDict
from datetime import datetime as _datetime, date as _date
from decimal import Decimal as _Decimal

from ..compat import six
from ..lib.xnamedtuple import xnamedtuple
from ..models import TableSchema, Column
from ..config import options
from ..types import DataType, Array, Map, Struct as _Struct, parse_composite_types


class Primitive(DataType):
    __slots__ = ()

    @property
    def CLASS_NAME(self):
        return self.__class__.__name__

    def cast_value(self, value, data_type):
        self._can_cast_or_throw(value, data_type)

        return value


class Integer(Primitive):
    __slots__ = ()

    def can_implicit_cast(self, other):
        if isinstance(other, six.string_types):
            other = validate_data_type(other)

        if isinstance(other, Integer) and other._n_bytes <= self._n_bytes:
            return True
        return False

    def validate_value(self, val, max_field_size=None):
        if val is None and self.nullable:
            return True
        return self._bounds[0] <= val <= self._bounds[1]


class Float(Primitive):
    __slots__ = ()

    def can_implicit_cast(self, other):
        if isinstance(other, six.string_types):
            other = validate_data_type(other)

        if isinstance(other, (Integer, Float)):
            return True
        return False

    def cast_value(self, value, data_type):
        self._can_cast_or_throw(value, data_type)

        return float(value)


class Int8(Integer):
    __slots__ = ()

    _n_bytes = 1
    _bounds = (-128, 127)


class Int16(Integer):
    __slots__ = ()

    _n_bytes = 2
    _bounds = (-32768, 32767)


class Int32(Integer):
    __slots__ = ()

    _n_bytes = 4
    _bounds = (-2147483648, 2147483647)


class Int64(Integer):
    __slots__ = ()

    _n_bytes = 8
    _bounds = (-9223372036854775808, 9223372036854775807)


class Float32(Float):
    __slots__ = ()

    _n_bytes = 4


class Float64(Float):
    __slots__ = ()

    _n_bytes = 8


class Datetime(Primitive):
    __slots__ = ()

    def can_implicit_cast(self, other):
        if isinstance(other, six.string_types):
            other = validate_data_type(other)

        if isinstance(other, (Datetime, String, Integer)):
            return True
        return False


class Date(Primitive):
    __slots__ = ()

    def can_implicit_cast(self, other):
        if isinstance(other, six.string_types):
            other = validate_data_type(other)

        if isinstance(other, (Timestamp, Datetime, String)):
            return True
        return False


class Timestamp(Primitive):
    __slots__ = ()

    def can_implicit_cast(self, other):
        if isinstance(other, six.string_types):
            other = validate_data_type(other)

        if isinstance(other, (Timestamp, Datetime, String)):
            return True
        return False


class Json(Primitive):
    __slots__ = ()


class Boolean(Primitive):
    __slots__ = ()


class Decimal(Primitive):
    __slots__ = ()

    def can_implicit_cast(self, other):
        if isinstance(other, (Decimal, Integer)):
            return True
        return False


class String(Primitive):
    __slots__ = ()


class Binary(Primitive):
    __slots__ = ()


class List(Array):
    __slots__ = ()
    CLASS_NAME = "List"

    def __init__(self, value_type, nullable=True):
        DataType.__init__(self, nullable=nullable)
        self.value_type = validate_data_type(value_type)

    def _equals(self, other):
        if isinstance(other, six.string_types):
            other = validate_data_type(other)

        return DataType._equals(self, other) and \
            self.value_type == other.value_type

    def can_implicit_cast(self, other):
        if isinstance(other, six.string_types):
            other = validate_data_type(other)

        return isinstance(other, List) and \
            self.value_type == other.value_type and \
            self.nullable == other.nullable


class Dict(Map):
    __slots__ = ()
    CLASS_NAME = "Dict"

    def __init__(self, key_type, value_type, nullable=True):
        DataType.__init__(self, nullable=nullable)
        self.key_type = validate_data_type(key_type)
        self.value_type = validate_data_type(value_type)

    def _equals(self, other):
        if isinstance(other, six.string_types):
            other = validate_data_type(other)

        return DataType._equals(self, other) and \
            self.key_type == other.key_type and \
            self.value_type == other.value_type

    def can_implicit_cast(self, other):
        if isinstance(other, six.string_types):
            other = validate_data_type(other)

        return isinstance(other, Dict) and \
            self.key_type == other.key_type and \
            self.value_type == other.value_type and \
            self.nullable == other.nullable


class Struct(_Struct):
    __slots__ = ()
    CLASS_NAME = "Struct"

    def __init__(self, field_types, nullable=True):
        DataType.__init__(self, nullable=nullable)
        self.field_types = OrderedDict()
        if isinstance(field_types, dict):
            field_types = six.iteritems(field_types)
        for k, v in field_types:
            self.field_types[k] = validate_data_type(v)
        self.namedtuple_type = xnamedtuple(
            "StructNamedTuple", list(self.field_types.keys())
        )
        self._struct_as_dict = options.struct_as_dict
        if self._struct_as_dict:
            self._use_ordered_dict = options.struct_as_ordered_dict
            if self._use_ordered_dict is None:
                self._use_ordered_dict = sys.version_info[:2] <= (3, 6)
        else:
            self._use_ordered_dict = False

    def _equals(self, other):
        if isinstance(other, six.string_types):
            other = validate_data_type(other)

        return isinstance(other, Struct) and \
            len(self.field_types) == len(other.field_types) and \
            all(self.field_types[k] == other.field_types[k] for k in six.iterkeys(self.field_types))

    def can_implicit_cast(self, other):
        if isinstance(other, six.string_types):
            other = validate_data_type(other)

        return isinstance(other, Struct) and self == other and \
            self.nullable == other.nullable


int8 = Int8()
int16 = Int16()
int32 = Int32()
int64 = Int64()
float32 = Float32()
float64 = Float64()
boolean = Boolean()
string = String()
decimal = Decimal()
datetime = Datetime()
date = Date()
timestamp = Timestamp()
binary = Binary()
json = Json()


_data_types = dict(
    (t.name, t) for t in
    (int8, int16, int32, int64, float32, float64,
     boolean, string, decimal, datetime, binary,
     date, timestamp)
)


_composite_handlers = dict(
    list=List,
    dict=Dict,
    struct=Struct,
)


def validate_data_type(data_type):
    if isinstance(data_type, DataType):
        return data_type

    if isinstance(data_type, type):
        data_type = data_type.__name__

    if isinstance(data_type, six.string_types):
        data_type = data_type.lower()
        if data_type == 'int':
            data_type = 'int64'
        elif data_type == 'float':
            data_type = 'float64'
        elif data_type == 'bool':
            data_type = 'boolean'
        if data_type in _data_types:
            return _data_types[data_type]

        composite_type = parse_composite_types(data_type, _composite_handlers)
        if composite_type:
            return composite_type

    raise ValueError('Invalid data type: %s' % repr(data_type))


def validate_value_type(value, data_type=None):
    try:
        from pandas import Timestamp
    except ImportError:
        Timestamp = None

    if data_type is not None:
        data_type.validate_value(value)
        return data_type

    inferred_value_type = None

    if isinstance(value, bool):
        inferred_value_type = boolean
    elif isinstance(value, six.integer_types):
        for t in (int8, int16, int32, int64):
            if t.validate_value(value):
                inferred_value_type = t
                break
        if inferred_value_type is None:
            raise ValueError('Integer value too large: %s' % value)
    elif isinstance(value, float):
        inferred_value_type = float64
    elif isinstance(value, six.string_types):
        inferred_value_type = string
    elif isinstance(value, _Decimal):
        inferred_value_type = decimal
    elif isinstance(value, _datetime):
        inferred_value_type = datetime
    elif isinstance(value, _date):
        inferred_value_type = date
    elif Timestamp is not None and isinstance(value, Timestamp):
        inferred_value_type = timestamp
    else:
        raise ValueError('Unknown value: %s, type: %s' % (value, type(value)))

    return inferred_value_type


_number_types = OrderedDict.fromkeys([
    int8, int16, int32, int64, float32, float64, decimal])


def number_types():
    return _number_types.keys()


def is_number(data_type):
    if not isinstance(data_type, DataType):
        data_type = validate_data_type(data_type)

    if data_type in _number_types:
        return True

    return False


class Unknown(DataType):
    __slots__ = 'type', # the type of the column and identify that it's a dynamic field
    _singleton = False
    CLASS_NAME = 'Unknown'

    def __init__(self, nullable=True, type=None):
        super(Unknown, self).__init__(nullable=nullable)
        self.type = type

    def _equals(self, other):
        # ``Unknown`` type is not equal to other types
        return False

    def can_implicit_cast(self, other):
        # ``Unknown`` can cast to other types
        return True


class DynamicSchema(TableSchema):
    def __init__(self, *args, **kwargs):
        self.default_type = kwargs.pop('default_type', None)
        super(DynamicSchema, self).__init__(*args, **kwargs)

    def __contains__(self, item):
        # We do not know the actual columns,
        # just return True
        return True

    def __eq__(self, other):
        return False

    def __getitem__(self, item):
        if isinstance(item, six.string_types):
            try:
                return super(DynamicSchema, self).__getitem__(item)
            except ValueError:
                return Column(name=item, type=Unknown(type=self.default_type))

        return super(DynamicSchema, self).__getitem__(item)

    def get_column(self, name):
        try:
            return super(DynamicSchema, self).get_column()
        except ValueError:
            return Column(name=name, type=Unknown(type=self.default_type))

    @classmethod
    def from_schema(cls, schema, default_type=None):
        if isinstance(schema, DynamicSchema):
            if default_type == schema.default_type:
                return schema
            default_type = default_type or schema.default_type
            return DynamicSchema(columns=schema._columns,
                                 default_type=default_type)
        return DynamicSchema(columns=schema._columns,
                             default_type=default_type)
