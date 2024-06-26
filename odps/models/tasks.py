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

import json  # don't remove
import random
import sys
import time
import warnings
from collections import OrderedDict

from .core import AbstractXMLRemoteModel
from .. import serializers, errors, utils
from ..compat import enum, six
from ..config import options


class Task(AbstractXMLRemoteModel):

    __slots__ = 'name', 'comment', 'properties'

    _type_indicator = 'type'

    name = serializers.XMLNodeField('Name')
    type = serializers.XMLTagField('.')
    comment = serializers.XMLNodeField('Comment')
    properties = serializers.XMLNodePropertiesField('Config', 'Property',
                                                    key_tag='Name', value_tag='Value')

    def __new__(cls, *args, **kwargs):
        typo = kwargs.get('type')

        if typo is not None:
            task_cls = None
            for v in six.itervalues(globals()):
                if not isinstance(v, type) or not issubclass(v, Task):
                    continue
                cls_type = getattr(v, '_root', v.__name__)
                if typo == cls_type:
                    task_cls = v
            if task_cls is None:
                task_cls = cls
        else:
            task_cls = cls

        return object.__new__(task_cls)

    def set_property(self, key, value):
        if self.properties is None:
            self.properties = OrderedDict()
        self.properties[key] = value

    def _update_property_json(self, field, value):
        def update(kv, dest):
            if not kv:
                return
            for k, v in six.iteritems(kv):
                if isinstance(v, bool):
                    dest[k] = 'true' if v else 'false'
                else:
                    dest[k] = str(v)

        if self.properties is None:
            self.properties = OrderedDict()
        if field in self.properties:
            settings = json.loads(self.properties[field])
        else:
            settings = OrderedDict()
        update(value, settings)
        self.properties[field] = json.dumps(settings)

    def update_settings(self, value):
        self._update_property_json('settings', value)

    def serialize(self):
        if type(self) is Task:
            raise errors.ODPSError('Unknown task type')
        return super(Task, self).serialize()

    @property
    def instance(self):
        return self.parent.parent

    @property
    def progress(self):
        """
        Get progress of a task.
        """
        return self.instance.get_task_progress(self.name)

    @property
    def stages(self):
        """
        Get execution stages of a task.
        """
        return self.instance.get_task_progress(self.name).stages

    @property
    def result(self):
        """
        Get execution result of the task.
        """
        return self.instance.get_task_result(self.name)

    @property
    def summary(self):
        """
        Get execution summary of the task.
        """
        return self.instance.get_task_summary(self.name)

    @property
    def detail(self):
        """
        Get execution details of the task.
        """
        return self.instance.get_task_detail(self.name)

    @property
    def quota(self):
        """
        Get quota json of the task.
        """
        return self.instance.get_task_quota(self.name)

    @property
    def workers(self):
        """
        Get workers of the task.
        """
        return self.instance.get_task_workers(self.name)

    def get_info(self, key):
        """
        Get associated information of the task.
        """
        return self.instance.get_task_info(self.name, key)

    def put_info(self, key, value):
        """
        Put associated information of the task.
        """
        return self.instance.put_task_info(self.name, key, value)


def format_cdata(query, semicolon=False):
    stripped_query = query.strip()
    if semicolon and not stripped_query.endswith(';'):
        stripped_query += ';'
    return '<![CDATA[%s]]>' % stripped_query


def collect_sql_settings(value, glob):
    from .. import __version__

    settings = OrderedDict()
    if options.default_task_settings:
        settings = options.default_task_settings

    settings["PYODPS_VERSION"] = __version__
    settings["PYODPS_PYTHON_VERSION"] = sys.version

    if glob:
        if options.sql.use_odps2_extension:
            settings['odps.sql.type.system.odps2'] = True
        if options.local_timezone is not None:
            if not options.local_timezone:
                settings['odps.sql.timezone'] = 'Etc/GMT'
            elif isinstance(options.local_timezone, bool):
                from ..lib import tzlocal

                zone = tzlocal.get_localzone()
                settings['odps.sql.timezone'] = utils.get_zone_name(zone)
            elif isinstance(options.local_timezone, six.string_types):
                settings['odps.sql.timezone'] = options.local_timezone
            else:
                zone = options.local_timezone
                zone_str = utils.get_zone_name(zone)
                if zone_str is None:
                    warnings.warn('Failed to get timezone string from options.local_timezone. '
                                  'You need to deal with timezone in the return data yourself.')
                else:
                    settings['odps.sql.timezone'] = zone_str
        if options.sql.settings:
            settings.update(options.sql.settings)
    if value:
        settings.update(value)
    return settings


class SQLTask(Task):
    __slots__ = '_anonymous_sql_task_name',

    _root = 'SQL'
    _anonymous_sql_task_name = 'AnonymousSQLTask'

    query = serializers.XMLNodeField('Query',
                                     serialize_callback=lambda s: format_cdata(s, True))

    def __init__(self, **kwargs):
        if 'name' not in kwargs:
            kwargs['name'] = SQLTask._anonymous_sql_task_name
        super(SQLTask, self).__init__(**kwargs)

    def serial(self):
        if self.properties is None:
            self.properties = OrderedDict()

        key = 'settings'
        if key not in self.properties:
            self.properties[key] = '{"odps.sql.udf.strict.mode": "true"}'

        return super(SQLTask, self).serial()

    def update_sql_settings(self, value=None, glob=True):
        settings = collect_sql_settings(value, glob)
        self.update_settings(settings)

    def update_aliases(self, value):
        self._update_property_json('aliases', value)

    @property
    def warnings(self):
        return json.loads(self.get_info('warnings')).get('warnings')


class MergeTask(Task):
    _root = 'Merge'

    table = serializers.XMLNodeField('TableName')

    def __init__(self, name=None, **kwargs):
        if name is None:
            name = 'merge_task_{0}_{1}'.format(int(time.time()), random.randint(100000, 999999))
        kwargs['name'] = name
        super(MergeTask, self).__init__(**kwargs)


class CupidTask(Task):
    _root = 'CUPID'

    plan = serializers.XMLNodeField('Plan', serialize_callback=format_cdata)

    def __init__(self, name=None, plan=None, hints=None, **kwargs):
        kwargs['name'] = name
        kwargs['plan'] = plan
        super(CupidTask, self).__init__(**kwargs)
        hints = hints or {}
        self.set_property('type', 'cupid')
        if hints:
            self.set_property('settings', json.dumps(hints))


class SQLCostTask(Task):
    __slots__ = '_anonymous_sql_cost_task_name',

    _root = 'SQLCost'
    _anonymous_sql_cost_task_name = 'AnonymousSQLCostTask'

    query = serializers.XMLNodeField('Query',
                                     serialize_callback=lambda s: format_cdata(s, True))

    def __init__(self, **kwargs):
        if 'name' not in kwargs:
            kwargs['name'] = self._anonymous_sql_cost_task_name
        super(SQLCostTask, self).__init__(**kwargs)

    def update_sql_cost_settings(self, value=None, glob=True):
        settings = collect_sql_settings(value, glob)
        self.update_settings(settings)


class SQLRTTask(Task):
    _root = "SQLRT"

    def update_sql_rt_settings(self, value=None, glob=True):
        settings = collect_sql_settings(value, glob)
        self.update_settings(settings)


class MaxFrameTask(Task):
    __slots__ = ("_output_format", "_major_version", "_service_endpoint")
    _root = "MaxFrame"
    _anonymous_task_name = "AnonymousMaxFrameTask"

    class CommandType(enum.Enum):
        CREATE_SESSION = "CREATE_SESSION"
        PYTHON_PACK = "PYTHON_PACK"

    command = serializers.XMLNodeField(
        "Command",
        default=CommandType.CREATE_SESSION,
        parse_callback=lambda t: MaxFrameTask.CommandType(t.upper()),
        serialize_callback=lambda t: t.value,
    )

    def __init__(self, **kwargs):
        kwargs["name"] = kwargs.get("name") or self._anonymous_task_name
        self._major_version = kwargs.pop("major_version", None)
        self._service_endpoint = kwargs.pop("service_endpoint", None)
        super(MaxFrameTask, self).__init__(**kwargs)

        if self.properties is None:
            self.properties = OrderedDict()
        self.properties["settings"] = "{}"

    def serial(self):
        if options.default_task_settings:
            settings = options.default_task_settings.copy()
        else:
            settings = OrderedDict()

        if self._major_version is not None:
            settings["odps.task.major.version"] = self._major_version
        if self._service_endpoint is not None:
            settings["odps.service.endpoint"] = self._service_endpoint

        if "settings" in self.properties:
            settings.update(json.loads(self.properties["settings"]))

        self.properties["settings"] = json.dumps(settings)
        return super(MaxFrameTask, self).serial()


try:
    from ..internal.models.tasks import *  # noqa: F401
except ImportError:
    pass
