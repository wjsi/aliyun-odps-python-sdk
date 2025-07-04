#!/usr/bin/env python
# -*- coding: utf-8 -*-
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

import warnings
from datetime import datetime

from .. import serializers, types, utils
from .core import JSONRemoteModel, LazyLoad, XMLRemoteModel
from .storage_tier import StorageTierInfo


class Partition(LazyLoad):
    """
    A partition is a collection of rows in a table whose partition columns are equal to specific
    values.

    In order to write data into partition, users should call the ``open_writer``
    method with **with statement**. At the same time, the ``open_reader`` method is used
    to provide the ability to read records from a partition. The behavior of these
    methods are the same as those in Table class except that there are no 'partition' params.
    """

    _extended_args = (
        "is_archived",
        "is_exstore",
        "lifecycle",
        "physical_size",
        "file_num",
        "reserved",
        "cdc_size",
        "cdc_record_num",
    )
    __slots__ = (
        "spec",
        "creation_time",
        "last_meta_modified_time",
        "last_data_modified_time",
        "last_access_time",
        "size",
        "record_num",
        "_is_extend_info_loaded",
    )
    __slots__ += _extended_args
    _extended_args = set(_extended_args)

    class Column(XMLRemoteModel):
        name = serializers.XMLNodeAttributeField(attr="Name")
        value = serializers.XMLNodeAttributeField(attr="Value")

    class PartitionMeta(JSONRemoteModel):
        creation_time = serializers.JSONNodeField(
            "createTime", parse_callback=datetime.fromtimestamp, set_to_parent=True
        )
        last_meta_modified_time = serializers.JSONNodeField(
            "lastDDLTime", parse_callback=datetime.fromtimestamp, set_to_parent=True
        )
        last_data_modified_time = serializers.JSONNodeField(
            "lastModifiedTime",
            parse_callback=datetime.fromtimestamp,
            set_to_parent=True,
        )
        last_access_time = serializers.JSONNodeField(
            "lastAccessTime",
            parse_callback=lambda x: datetime.fromtimestamp(x) if x else None,
            set_to_parent=True,
        )
        size = serializers.JSONNodeField(
            "partitionSize", parse_callback=int, set_to_parent=True
        )
        record_num = serializers.JSONNodeField(
            "partitionRecordNum", parse_callback=int, set_to_parent=True
        )

    class PartitionExtendedMeta(PartitionMeta):
        is_archived = serializers.JSONNodeField(
            "IsArchived", parse_callback=bool, set_to_parent=True
        )
        is_exstore = serializers.JSONNodeField(
            "IsExstore", parse_callback=bool, set_to_parent=True
        )
        lifecycle = serializers.JSONNodeField(
            "LifeCycle", parse_callback=int, set_to_parent=True
        )
        physical_size = serializers.JSONNodeField(
            "PhysicalSize", parse_callback=int, set_to_parent=True
        )
        file_num = serializers.JSONNodeField(
            "FileNum", parse_callback=int, set_to_parent=True
        )
        reserved = serializers.JSONNodeField(
            "Reserved", type="json", set_to_parent=True
        )

    columns = serializers.XMLNodesReferencesField(Column, "Column")
    _schema = serializers.XMLNodeReferenceField(PartitionMeta, "Schema")
    _extended_schema = serializers.XMLNodeReferenceField(
        PartitionExtendedMeta, "Schema"
    )
    creation_time = serializers.XMLNodeField(
        "CreationTime", parse_callback=lambda x: datetime.fromtimestamp(int(x))
    )
    last_meta_modified_time = serializers.XMLNodeField(
        "LastDDLTime", parse_callback=lambda x: datetime.fromtimestamp(int(x))
    )
    last_data_modified_time = serializers.XMLNodeField(
        "LastModifiedTime", parse_callback=lambda x: datetime.fromtimestamp(int(x))
    )
    size = serializers.XMLNodeField("PartitionSize", parse_callback=int)
    record_num = serializers.XMLNodeField("PartitionRecordCount", parse_callback=int)

    def __init__(self, **kwargs):
        self._is_extend_info_loaded = False

        super(Partition, self).__init__(**kwargs)

    def __str__(self):
        return str(self.partition_spec)

    def __repr__(self):
        return "<Partition %s.%s(%s)>" % (
            str(self.table.project.name),
            str(utils.backquote_string(self.table.name)),
            str(self.partition_spec),
        )

    def _is_field_set(self, attr):
        try:
            attr_val = self._getattr(attr)
        except AttributeError:
            return False

        if attr in ("size", "record_num") and attr_val is not None and attr_val >= 0:
            return True
        return attr_val is not None

    def __getattribute__(self, attr):
        if attr in type(self)._extended_args:
            if not self._is_extend_info_loaded and not self._is_field_set(attr):
                self.reload_extend_info()

            return object.__getattribute__(self, attr)

        val = object.__getattribute__(self, attr)
        if val is None and not self._loaded:
            if attr in getattr(Partition.PartitionMeta, "__fields"):
                self.reload()
                return object.__getattribute__(self, attr)

        return super(Partition, self).__getattribute__(attr)

    def _set_state(self, name, parent, client):
        self.__init__(spec=name, _parent=parent, _client=client)

    def _name(self):
        return

    @classmethod
    def get_partition_spec(cls, columns=None, spec=None):
        if spec is not None:
            return spec

        spec = types.PartitionSpec()
        for col in columns:
            spec[col.name] = col.value

        return spec

    @property
    def last_modified_time(self):
        warnings.warn(
            "Partition.last_modified_time is deprecated and will be replaced by "
            "Partition.last_data_modified_time.",
            DeprecationWarning,
            stacklevel=3,
        )
        utils.add_survey_call(
            ".".join([type(self).__module__, type(self).__name__, "last_modified_time"])
        )
        return self.last_data_modified_time

    @property
    def partition_spec(self):
        return self.get_partition_spec(self._getattr("columns"), self._getattr("spec"))

    @property
    def name(self):
        return str(self.partition_spec)

    @property
    def table(self):
        return self.parent.parent

    @property
    def project(self):
        return self.table.project

    @property
    def storage_tier_info(self):
        return StorageTierInfo.deserial(self.reserved)

    def reload(self):
        url = self.resource()
        params = {"partition": str(self.partition_spec)}
        resp = self._client.get(url, params=params, curr_schema=self._get_schema_name())

        self.parse(self._client, resp, obj=self)

        self._loaded = True

    def reload_extend_info(self):
        url = self.resource()
        params = {"partition": str(self.partition_spec)}
        resp = self._client.get(
            url, action="extended", params=params, curr_schema=self._get_schema_name()
        )

        self.parse(self._client, resp, obj=self)
        self._is_extend_info_loaded = True

        self._parse_reserved()

    def _parse_reserved(self):
        if not self.reserved:
            self.cdc_size = -1
            self.cdc_record_num = -1
            return
        self.cdc_size = int(self.reserved.get("cdc_size", "-1"))
        self.cdc_record_num = int(self.reserved.get("cdc_record_num", "-1"))

    def head(self, limit, columns=None):
        """
        Get the head records of a partition

        :param limit: records' size, 10000 at most
        :param list columns: the columns which is subset of the table columns
        :return: records
        :rtype: list

        .. seealso:: :class:`odps.models.Record`
        """
        return self.table.head(limit, partition=self.partition_spec, columns=columns)

    def to_df(self):
        """
        Create a PyODPS DataFrame from this partition.

        :return: DataFrame object
        """
        from ..df import DataFrame

        return DataFrame(self.table).filter_parts(self)

    @utils.with_wait_argument
    def drop(self, async_=False, if_exists=False):
        """
        Drop this partition.

        :param async_: run asynchronously if True
        :param if_exists:
        :return: None
        """
        return self.parent.delete(self, if_exists=if_exists, async_=async_)

    def open_reader(self, **kw):
        """
        Open the reader to read the entire records from this partition.

        :param reopen: the reader will reuse last one, reopen is true means open a new reader.
        :type reopen: bool
        :param endpoint: the tunnel service URL
        :param compress_option: compression algorithm, level and strategy
        :type compress_option: :class:`odps.tunnel.CompressOption`
        :param compress_algo: compression algorithm, work when ``compress_option`` is not provided,
                              can be ``zlib``, ``snappy``
        :param compress_level: used for ``zlib``, work when ``compress_option`` is not provided
        :param compress_strategy: used for ``zlib``, work when ``compress_option`` is not provided
        :return: reader, ``count`` means the full size, ``status`` means the tunnel status

        :Example:

        >>> with partition.open_reader() as reader:
        >>>     count = reader.count  # How many records of a partition
        >>>     for record in reader[0: count]:
        >>>         # read all data, actually better to split into reading for many times
        """
        return self.table.open_reader(str(self), **kw)

    def open_writer(self, blocks=None, **kw):
        return self.table.open_writer(self.partition_spec, blocks=blocks, **kw)

    def to_pandas(
        self,
        columns=None,
        start=None,
        count=None,
        n_process=1,
        quota_name=None,
        append_partitions=None,
        tags=None,
        **kwargs
    ):
        """
        Read partition data into pandas DataFrame

        :param list columns: columns to read
        :param int start: start row index from 0
        :param int count: data count to read
        :param int n_process: number of processes to accelerate reading
        :param str quota_name: name of tunnel quota to use
        :param bool append_partitions: if True, partition values will be
            appended to the output
        """
        try:
            import pyarrow as pa
        except ImportError:
            pa = None

        arrow = (pa is not None) and kwargs.pop("arrow", True)
        return self.table.to_pandas(
            partition=self.partition_spec,
            columns=columns,
            arrow=arrow,
            quota_name=quota_name,
            tags=tags,
            n_process=n_process,
            start=start,
            count=count,
            append_partitions=append_partitions,
            **kwargs
        )

    def iter_pandas(
        self,
        columns=None,
        batch_size=None,
        start=None,
        count=None,
        quota_name=None,
        append_partitions=None,
        tags=None,
        **kwargs
    ):
        """
        Read partition data into pandas DataFrame

        :param list columns: columns to read
        :param int batch_size: size of DataFrame batch to read
        :param int start: start row index from 0
        :param int count: data count to read
        :param str quota_name: name of tunnel quota to use
        :param bool append_partitions: if True, partition values will be
            appended to the output
        """
        for batch in self.table.iter_pandas(
            partition=self.partition_spec,
            columns=columns,
            batch_size=batch_size,
            arrow=True,
            quota_name=quota_name,
            tags=tags,
            append_partitions=append_partitions,
            start=start,
            count=count,
            **kwargs
        ):
            yield batch

    @utils.with_wait_argument
    def truncate(self, async_=False):
        """
        Truncate current partition.
        """
        return self.table.truncate(self.partition_spec, async_=async_)

    def _unload_if_async(self, async_=False, reload=True):
        self._is_extend_info_loaded = False
        if async_:
            self._loaded = False
        elif reload:
            self.reload()

    @utils.with_wait_argument
    def set_storage_tier(self, storage_tier, async_=False, hints=None):
        """
        Set storage tier of current partition.
        """
        inst = self.table.set_storage_tier(
            storage_tier, partition_spec=self.partition_spec, async_=async_, hints=hints
        )
        self._unload_if_async(async_)
        return inst

    @utils.with_wait_argument
    def change_partition_spec(self, new_partition_spec, async_=False, hints=None):
        """
        Change partition spec of current partition.

        :param new_partition_spec: new partition spec
        """
        inst = self.table.change_partition_spec(
            self.partition_spec,
            new_partition_spec,
            async_=async_,
            hints=hints,
        )
        self.spec = types.PartitionSpec(new_partition_spec)
        self._unload_if_async(async_)
        return inst

    @utils.with_wait_argument
    def touch(self, async_=False, hints=None):
        """
        Update the last modified time of the partition.
        """
        inst = self.table.touch(
            partition_spec=self.partition_spec, async_=async_, hints=hints
        )
        self._unload_if_async(async_)
        return inst
