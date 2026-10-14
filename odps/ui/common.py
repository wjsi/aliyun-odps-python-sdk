# -*- coding: utf-8 -*-
# Copyright 1999-2026 Alibaba Group Holding Ltd.
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

MAX_SCRIPT_LOAD_SEC = 5
SCRIPT_LOAD_CHECK_INTERVAL = 0.01


try:
    from ..console import in_ipython_frontend, ipython_major_version, widgets

    if any(v is None for v in (widgets, ipython_major_version, in_ipython_frontend)):
        raise ImportError

    from traitlets import List, Unicode  # noqa: F401
except Exception:
    InstancesProgress = None
    build_trait = None
    in_ipython_frontend = None
else:
    last_ipython_msg_id = None

    def build_trait(trait_cls, default_value=None, **metadata):
        if default_value:
            return trait_cls(default_value).tag(**metadata)
        else:
            return trait_cls().tag(**metadata)
