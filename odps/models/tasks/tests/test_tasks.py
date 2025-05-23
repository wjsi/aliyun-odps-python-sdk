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

import json
import sys

import pytest

from ....config import options
from ....errors import ODPSError
from ....utils import get_zone_name, to_text
from .. import CupidTask, MaxFrameTask, SQLCostTask, SQLTask, Task

try:
    import zoneinfo
except ImportError:
    zoneinfo = None
try:
    import pytz
except ImportError:
    pytz = None


sql_template = """<?xml version="1.0" encoding="utf-8"?>
<SQL>
  <Name>AnonymousSQLTask</Name>
  <Config>
    <Property>
      <Name>settings</Name>
      <Value>{"odps.sql.udf.strict.mode": "true"}</Value>
    </Property>
  </Config>
  <Query><![CDATA[%(sql)s;]]></Query>
</SQL>
"""

sql_tz_template = """<?xml version="1.0" encoding="utf-8"?>
<SQL>
  <Name>AnonymousSQLTask</Name>
  <Config>
    <Property>
      <Name>settings</Name>
      <Value>{"PYODPS_VERSION": "%(pyodps_version)s", "PYODPS_PYTHON_VERSION": %(python_version)s, "odps.sql.timezone": "%(tz)s"}</Value>
    </Property>
  </Config>
  <Query><![CDATA[%(sql)s;]]></Query>
</SQL>
"""

cupid_template = """<?xml version="1.0" encoding="utf-8"?>
<CUPID>
  <Name>task_1</Name>
  <Config>
    <Property>
      <Name>type</Name>
      <Value>cupid</Value>
    </Property>
    <Property>
      <Name>settings</Name>
      <Value>{"odps.cupid.wait.am.start.time": 600}</Value>
    </Property>
  </Config>
  <Plan><![CDATA[plan_text]]></Plan>
</CUPID>
"""

sql_cost_template = """<?xml version="1.0" encoding="utf-8"?>
<SQLCost>
  <Name>AnonymousSQLCostTask</Name>
  <Query><![CDATA[%(sql)s;]]></Query>
</SQLCost>
"""

maxframe_template = """<?xml version="1.0" encoding="utf-8"?>
<MaxFrame>
  <Name>AnonymousMaxFrameTask</Name>
  <Config>
    <Property>
      <Name>settings</Name>
      <Value>{"odps.service.endpoint": "%(endpoint)s", "odps.maxframe.output_format": "maxframe_v1"}</Value>
    </Property>
  </Config>
  <Command>CREATE_SESSION</Command>
</MaxFrame>
"""

mf_ray_cluster_init_template = """<?xml version="1.0" encoding="utf-8"?>
<MaxFrame>
  <Name>AnonymousMaxFrameTask</Name>
  <Config>
    <Property>
      <Name>settings</Name>
      <Value>{"odps.maxframe.output_format": "maxframe_v1"}</Value>
    </Property>
    <Property>
      <Name>cloudId</Name>
      <Value>%(cloud_id)s</Value>
    </Property>
    <Property>
      <Name>regionId</Name>
      <Value>%(region_id)s</Value>
    </Property>
    <Property>
      <Name>quotaNick</Name>
      <Value>%(quota_nick)s</Value>
    </Property>
  </Config>
  <Command>RAY_CLUSTER_INIT</Command>
</MaxFrame>
"""


def test_task_class_type():
    typed = Task(type="SQL", query="select * from dual")
    assert isinstance(typed, SQLTask)

    unknown_typed = Task(type="UnknownType")
    assert type(unknown_typed) is Task
    pytest.raises(ODPSError, lambda: unknown_typed.serialize())

    untyped = Task()
    assert type(untyped) is Task
    pytest.raises(ODPSError, lambda: untyped.serialize())


def test_sql_task_to_xml():
    query = "select * from dual"

    task = SQLTask(query=query)
    to_xml = task.serialize()
    right_xml = sql_template % {"sql": query}

    assert to_text(to_xml) == to_text(right_xml)

    task = Task.parse(None, to_xml)
    assert isinstance(task, SQLTask)


@pytest.mark.skipif(pytz is None and zoneinfo is None, reason="pytz not installed")
def test_sql_task_to_xml_timezone():
    from .... import __version__
    from ....lib import tzlocal

    query = "select * from dual"
    versions = {
        "pyodps_version": __version__,
        "python_version": json.dumps(sys.version),
    }

    def _format_template(**kwargs):
        kwargs.update(versions)
        return sql_tz_template % kwargs

    try:
        options.local_timezone = True
        local_zone = tzlocal.get_localzone()
        local_zone_name = get_zone_name(local_zone)
        task = SQLTask(query=query)
        task.update_sql_settings()
        to_xml = task.serialize()
        right_xml = _format_template(sql=query, tz=local_zone_name)

        assert to_text(to_xml) == to_text(right_xml)

        options.local_timezone = False
        task = SQLTask(query=query)
        task.update_sql_settings()
        to_xml = task.serialize()
        right_xml = _format_template(sql=query, tz="Etc/GMT")

        assert to_text(to_xml) == to_text(right_xml)

        if zoneinfo:
            options.local_timezone = zoneinfo.ZoneInfo("Asia/Shanghai")
            task = SQLTask(query=query)
            task.update_sql_settings()
            to_xml = task.serialize()
            right_xml = _format_template(sql=query, tz=options.local_timezone.key)

            assert to_text(to_xml) == to_text(right_xml)

        if pytz:
            options.local_timezone = pytz.timezone("Asia/Shanghai")
            task = SQLTask(query=query)
            task.update_sql_settings()
            to_xml = task.serialize()
            right_xml = _format_template(sql=query, tz=options.local_timezone.zone)

            assert to_text(to_xml) == to_text(right_xml)
    finally:
        options.local_timezone = None


def test_cupid_task_to_xml():
    task = CupidTask("task_1", "plan_text", {"odps.cupid.wait.am.start.time": 600})
    to_xml = task.serialize()
    right_xml = cupid_template

    assert to_text(to_xml) == to_text(right_xml)

    task = Task.parse(None, to_xml)
    assert isinstance(task, CupidTask)


def test_sql_cost_task_to_xml():
    query = "select * from dual"
    task = SQLCostTask(query=query)
    to_xml = task.serialize()
    right_xml = sql_cost_template % {"sql": query}

    assert to_text(to_xml) == to_text(right_xml)

    task = Task.parse(None, to_xml)
    assert isinstance(task, SQLCostTask)


def test_maxframe_task_to_xml(odps):
    task = MaxFrameTask(service_endpoint=odps.endpoint)
    task.update_settings({"odps.maxframe.output_format": "maxframe_v1"})
    to_xml = task.serialize()
    right_xml = maxframe_template % {"endpoint": odps.endpoint}

    assert to_text(to_xml) == to_text(right_xml)

    task = Task.parse(None, to_xml)
    assert isinstance(task, MaxFrameTask)
    assert task.command == MaxFrameTask.CommandType.CREATE_SESSION


def test_ray_cluster_init(odps):
    task = MaxFrameTask(command=MaxFrameTask.CommandType.RAY_CLUSTER_INIT)
    cloud_id = "test-cloudid"
    region_id = "test-regionId"
    quota_nick = "test-quotaNick"
    task.update_settings({"odps.maxframe.output_format": "maxframe_v1"})
    task.set_property("cloudId", cloud_id)
    task.set_property("regionId", region_id)
    task.set_property("quotaNick", quota_nick)
    to_xml = task.serialize()
    right_xml = mf_ray_cluster_init_template % {
        "cloud_id": cloud_id,
        "region_id": region_id,
        "quota_nick": quota_nick,
    }
    assert to_text(to_xml) == to_text(right_xml)
    task = Task.parse(None, to_xml)
    assert isinstance(task, MaxFrameTask)
    assert task.command == MaxFrameTask.CommandType.RAY_CLUSTER_INIT
