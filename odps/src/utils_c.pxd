# Copyright 1999-2025 Alibaba Group Holding Ltd.
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

from cpython.datetime cimport date, datetime
from libc.stdint cimport int32_t, int64_t
from libc.time cimport tm


cdef class CMillisecondsConverter:
    cdef:
        object _local_tz, _tz
        bint _use_default_tz
        bint _default_tz_local
        bint _allow_antique
        bint _is_dst
        bint _tz_has_localize

    cdef int _build_tm_struct(self, datetime dt, tm *p_tm) except? -1
    cpdef int64_t to_milliseconds(self, datetime dt) except? -1
    cpdef datetime from_milliseconds(self, int64_t milliseconds)

cdef int32_t to_days(date py_date) except? -1
cdef to_date(int32_t days)

cpdef inline str to_str(s, encoding=*)
cpdef inline bytes to_binary(s, encoding=*)
cpdef inline unicode to_text(s, encoding=*)
cpdef str to_lower_str(s, encoding=*)
