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

import collections
import functools
import json
import struct
import sys
import warnings
from collections import OrderedDict
from decimal import Decimal
from io import BytesIO, IOBase, StringIO

try:
    import numpy as np
except ImportError:
    np = None
try:
    import pandas as pd
except (ImportError, ValueError):
    pd = None
try:
    import pyarrow as pa
except (AttributeError, ImportError):
    pa = None
try:
    import pyarrow.compute as pac
except (AttributeError, ImportError):
    pac = None

from ... import compat, types, utils
from ...config import options
from ...errors import ChecksumError, DatetimeOverflowError
from ...lib.monotonic import monotonic
from ...models import Record
from ...readers import AbstractRecordReader
from ...types import PartitionSpec
from ..base import TunnelMetrics
from ..checksum import Checksum
from ..pb import wire_format
from ..pb.decoder import Decoder
from ..pb.errors import DecodeError
from ..wireconstants import ProtoWireConstants
from .types import odps_schema_to_arrow_schema

try:
    if not options.force_py:
        from .reader_c import BaseTunnelRecordReader, convert_legacy_decimal_bytes
    else:
        BaseTunnelRecordReader = convert_legacy_decimal_bytes = None
except ImportError as e:
    if options.force_c:
        raise e
    BaseTunnelRecordReader = convert_legacy_decimal_bytes = None

MICRO_SEC_PER_SEC = 1000000

if BaseTunnelRecordReader is None:

    class BaseTunnelRecordReader(AbstractRecordReader):
        def __init__(
            self,
            schema,
            stream_creator,
            columns=None,
            partition_spec=None,
            append_partitions=False,
        ):
            self._schema = schema
            if columns is None:
                self._columns = (
                    self._schema.columns
                    if append_partitions
                    else self._schema.simple_columns
                )
            else:
                self._columns = [self._schema[c] for c in columns]

            self._enable_client_metrics = options.tunnel.enable_client_metrics
            self._server_metrics_string = None
            self._local_wall_time_ms = 0
            self._acc_network_time_ms = 0
            self._injected_error = None

            self._curr_cursor = 0
            self._stream_creator = stream_creator
            self._reader = None
            self._reopen_reader()

            if self._enable_client_metrics:
                ts = monotonic()

            self._read_limit = options.table_read_limit
            self._to_datetime = utils.MillisecondsConverter().from_milliseconds
            self._to_datetime_utc = utils.MillisecondsConverter(
                local_tz=False
            ).from_milliseconds
            self._to_date = utils.to_date
            self._partition_spec = (
                PartitionSpec(partition_spec) if partition_spec else None
            )
            self._append_partitions = append_partitions

            map_as_ordered_dict = options.map_as_ordered_dict
            if map_as_ordered_dict is None:
                map_as_ordered_dict = sys.version_info[:2] <= (3, 6)
            self._map_dict_hook = OrderedDict if map_as_ordered_dict else dict

            struct_as_ordered_dict = options.struct_as_ordered_dict
            if struct_as_ordered_dict is None:
                struct_as_ordered_dict = sys.version_info[:2] <= (3, 6)
            self._struct_dict_hook = OrderedDict if struct_as_ordered_dict else dict

            if self._enable_client_metrics:
                self._local_wall_time_ms += compat.long_type(
                    MICRO_SEC_PER_SEC * (monotonic() - ts)
                )

        def _mode(self):
            return "py"

        @property
        def count(self):
            return self._curr_cursor

        @property
        def _network_wall_time_ms(self):
            return self._reader.network_wall_time_ms + self._acc_network_time_ms

        def _inject_error(self, cursor, exc):
            self._injected_error = (cursor, exc)

        def _reopen_reader(self):
            if self._enable_client_metrics:
                ts = monotonic()

            stream = self._stream_creator(self._curr_cursor)
            if self._enable_client_metrics:
                self._acc_network_time_ms += compat.long_type(
                    MICRO_SEC_PER_SEC * (monotonic() - ts)
                )
                if self._reader is not None:
                    self._acc_network_time_ms += self._reader.network_wall_time_ms

            self._last_n_bytes = len(self._reader) if self._curr_cursor != 0 else 0
            self._reader = Decoder(
                stream, record_network_time=self._enable_client_metrics
            )
            self._crc = Checksum()
            self._crccrc = Checksum()
            self._attempt_row_count = 0

            if self._enable_client_metrics:
                self._local_wall_time_ms += compat.long_type(
                    MICRO_SEC_PER_SEC * (monotonic() - ts)
                )

        def _read_field(self, data_type):
            if data_type == types.float_:
                val = self._reader.read_float()
                self._crc.update_float(val)
            elif data_type == types.double:
                val = self._reader.read_double()
                self._crc.update_double(val)
            elif data_type == types.boolean:
                val = self._reader.read_bool()
                self._crc.update_bool(val)
            elif data_type in types.integer_types:
                val = self._reader.read_sint64()
                self._crc.update_long(val)
            elif data_type == types.string:
                val = self._reader.read_string()
                self._crc.update(val)
            elif data_type == types.binary:
                val = self._reader.read_string()
                self._crc.update(val)
            elif data_type == types.datetime:
                val = self._reader.read_sint64()
                self._crc.update_long(val)
                try:
                    val = self._to_datetime(val)
                except DatetimeOverflowError:
                    if not options.tunnel.overflow_date_as_none:
                        raise
                    val = None
            elif data_type == types.date:
                val = self._reader.read_sint64()
                self._crc.update_long(val)
                val = self._to_date(val)
            elif data_type == types.timestamp or data_type == types.timestamp_ntz:
                to_datetime = (
                    self._to_datetime_utc
                    if data_type == types.timestamp_ntz
                    else self._to_datetime
                )
                l_val = self._reader.read_sint64()
                self._crc.update_long(l_val)
                nano_secs = self._reader.read_sint32()
                self._crc.update_int(nano_secs)
                if pd is None:
                    raise ImportError(
                        "To use TIMESTAMP in pyodps, you need to install pandas."
                    )
                try:
                    val = pd.Timestamp(to_datetime(l_val * 1000)) + pd.Timedelta(
                        nanoseconds=nano_secs
                    )
                except DatetimeOverflowError:
                    if not options.tunnel.overflow_date_as_none:
                        raise
                    val = None
            elif data_type == types.interval_day_time:
                l_val = self._reader.read_sint64()
                self._crc.update_long(l_val)
                nano_secs = self._reader.read_sint32()
                self._crc.update_int(nano_secs)
                if pd is None:
                    raise ImportError(
                        "To use INTERVAL_DAY_TIME in pyodps, you need to install pandas."
                    )
                val = pd.Timedelta(seconds=l_val, nanoseconds=nano_secs)
            elif data_type == types.interval_year_month:
                l_val = self._reader.read_sint64()
                self._crc.update_long(l_val)
                val = compat.Monthdelta(l_val)
            elif data_type == types.json:
                sval = self._reader.read_string()
                val = json.loads(sval)
                self._crc.update(sval)
            elif isinstance(data_type, (types.Char, types.Varchar)):
                val = self._reader.read_string()
                self._crc.update(val)
            elif isinstance(data_type, types.Decimal):
                val = self._reader.read_string()
                self._crc.update(val)
            elif isinstance(data_type, types.Array):
                val = self._read_array(data_type.value_type)
            elif isinstance(data_type, types.Map):
                keys = self._read_array(data_type.key_type)
                values = self._read_array(data_type.value_type)
                val = self._map_dict_hook(zip(keys, values))
            elif isinstance(data_type, types.Struct):
                val = self._read_struct(data_type)
            else:
                raise IOError("Unsupported type %s" % data_type)
            return val

        def _read_array(self, value_type):
            res = []

            size = self._reader.read_uint32()
            for _ in range(size):
                if self._reader.read_bool():
                    res.append(None)
                else:
                    res.append(self._read_field(value_type))

            return res

        def _read_struct(self, value_type):
            res_list = [None] * len(value_type.field_types)
            for idx, field_type in enumerate(value_type.field_types.values()):
                if not self._reader.read_bool():
                    res_list[idx] = self._read_field(field_type)
            if options.struct_as_dict:
                return self._struct_dict_hook(
                    zip(value_type.field_types.keys(), res_list)
                )
            else:
                return value_type.namedtuple_type(*res_list)

        def _read_single_record(self):
            if (
                self._injected_error is not None
                and self._injected_error[0] == self._curr_cursor
            ):
                self._injected_error = None
                raise self._injected_error[1]

            if self._read_limit is not None and self.count >= self._read_limit:
                warnings.warn(
                    "Number of lines read via tunnel already reaches the limitation.",
                    RuntimeWarning,
                )
                return None

            record = Record(self._columns, max_field_size=(1 << 63) - 1)

            while True:
                index, _ = self._reader.read_field_number_and_wire_type()

                if index == 0:
                    continue
                if index == ProtoWireConstants.TUNNEL_END_RECORD:
                    checksum = utils.long_to_int(self._crc.getvalue())
                    if int(self._reader.read_uint32()) != utils.int_to_uint(checksum):
                        raise ChecksumError("Checksum invalid")
                    self._crc.reset()
                    self._crccrc.update_int(checksum)
                    break

                if index == ProtoWireConstants.TUNNEL_META_COUNT:
                    if self._attempt_row_count != self._reader.read_sint64():
                        raise IOError("count does not match")

                    (
                        idx_of_checksum,
                        wire_type,
                    ) = self._reader.read_field_number_and_wire_type()
                    if ProtoWireConstants.TUNNEL_META_CHECKSUM != idx_of_checksum:
                        if wire_type != wire_format.WIRETYPE_LENGTH_DELIMITED:
                            raise IOError("Invalid stream data.")
                        self._crc.update_int(idx_of_checksum)

                        self._server_metrics_string = self._reader.read_string()
                        self._crc.update(self._server_metrics_string)

                        idx_of_checksum = (
                            self._reader.read_field_number_and_wire_type()[0]
                        )
                        if idx_of_checksum != ProtoWireConstants.TUNNEL_END_METRICS:
                            raise IOError("Invalid stream data.")
                        checksum = utils.long_to_int(self._crc.getvalue())
                        self._crc.reset()
                        if utils.int_to_uint(checksum) != int(
                            self._reader.read_uint32()
                        ):
                            raise ChecksumError("Checksum invalid.")

                        idx_of_checksum = (
                            self._reader.read_field_number_and_wire_type()[0]
                        )
                    if ProtoWireConstants.TUNNEL_META_CHECKSUM != idx_of_checksum:
                        raise IOError("Invalid stream data.")
                    if int(self._crccrc.getvalue()) != self._reader.read_uint32():
                        raise ChecksumError("Checksum invalid.")

                    return

                if index > len(self._columns):
                    raise IOError(
                        "Invalid protobuf tag. Perhaps the datastream "
                        "from server is crushed."
                    )

                self._crc.update_int(index)

                i = index - 1
                record[i] = self._read_field(self._columns[i].type)

            if self._append_partitions and self._partition_spec is not None:
                for k, v in self._partition_spec.items():
                    try:
                        record[k] = v
                    except KeyError:
                        # skip non-existing fields
                        pass

            self._curr_cursor += 1
            self._attempt_row_count += 1
            return record

        def read(self):
            if self._enable_client_metrics:
                ts = monotonic()
            result = utils.call_with_retry(
                self._read_single_record, reset_func=self._reopen_reader
            )
            if self._enable_client_metrics:
                self._local_wall_time_ms += int(MICRO_SEC_PER_SEC * (monotonic() - ts))
            return result

        def reads(self):
            return self.__iter__()

        @property
        def n_bytes(self):
            return self._last_n_bytes + len(self._reader)

        def get_total_bytes(self):
            return self.n_bytes


class TunnelRecordReader(BaseTunnelRecordReader, AbstractRecordReader):
    """
    Reader object to read data from ODPS in records. Should be created
    with :meth:`TableDownloadSession.open_record_reader`.

    :Example:

    .. code-block:: python

        from odps.tunnel import TableTunnel

            tunnel = TableTunnel(o)
            download_session = tunnel.create_download_session('my_table', partition_spec='pt=test')

            # create a TunnelRecordReader
            with download_session.open_record_reader(0, download_session.count) as reader:
                for record in reader:
                    print(record.values)
    """

    def __next__(self):
        record = self.read()
        if record is None:
            raise StopIteration
        return record

    next = __next__

    @property
    def schema(self):
        return self._schema

    @property
    def metrics(self):
        if self._server_metrics_string is None:
            return None
        return TunnelMetrics.from_server_json(
            type(self).__name__,
            self._server_metrics_string,
            self._local_wall_time_ms,
            self._network_wall_time_ms,
        )

    def close(self):
        if hasattr(self._schema, "close"):
            self._schema.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


try:
    TunnelRecordReader.read.__doc__ = """
    Read next record.

    :return: A record object
    :rtype: :class:`~odps.models.Record`
    """
except:
    pass


class ArrowStreamReader(IOBase):
    def __init__(self, raw_reader, arrow_schema):
        self._reader = raw_reader

        self._crc = Checksum()
        self._crccrc = Checksum()
        self._pos = 0
        self._chunk_size = None

        self._buffers = collections.deque()
        self._buffers.append(BytesIO(arrow_schema.serialize().to_pybytes()))

    def __len__(self):
        return len(self._reader)

    def readable(self):
        return True

    @staticmethod
    def _read_unint32(b):
        return struct.unpack("!I", b)

    def _read_chunk_size(self):
        try:
            i = self._read_unint32(self._reader.read(4))
            self._pos += 4
            return i[0]  # unpack() result is a 1-element tuple.
        except struct.error as e:
            raise DecodeError(e)

    def _read_chunk(self):
        read_size = self._chunk_size + 4
        b = self._reader.read(read_size)
        if 0 < len(b) < 4:
            raise ChecksumError("Checksum invalid")
        self._pos += len(b)
        self._crc.update(b[:-4])
        self._crccrc.update(b[:-4])
        return b

    def _fill_next_buffer(self):
        if self._chunk_size is None:
            self._chunk_size = self._read_chunk_size()

        b = self._read_chunk()
        data = b[:-4]
        crc_data = b[-4:]
        if len(b) == 0:
            return

        if len(b) < self._chunk_size + 4:
            # is last chunk
            read_checksum = self._read_unint32(crc_data)[0]
            checksum = int(self._crccrc.getvalue())
            if checksum != read_checksum:
                raise ChecksumError("Checksum invalid")
            self._pos += len(data) + 4
            self._buffers.append(BytesIO(data))
            self._crccrc.reset()
        else:
            checksum = int(self._crc.getvalue())
            read_checksum = self._read_unint32(crc_data)[0]
            if checksum != read_checksum:
                raise ChecksumError("Checksum invalid")
            self._crc.reset()
            self._buffers.append(BytesIO(data))

    def read(self, nbytes=None):
        tot_size = 0
        bufs = []
        while nbytes is None or tot_size < nbytes:
            if not self._buffers:
                self._fill_next_buffer()
                if not self._buffers:
                    break

            to_read = nbytes - tot_size if nbytes is not None else None
            buf = self._buffers[0].read(to_read)
            if not buf:
                self._buffers.popleft()
            else:
                bufs.append(buf)
                tot_size += len(buf)
        if len(bufs) == 1:
            return bufs[0]
        return b"".join(bufs)

    def close(self):
        if hasattr(self._reader, "close"):
            self._reader.close()


class TunnelArrowReader(object):
    """
    Reader object to read data from ODPS in Arrow format. Should be created
    with :meth:`TableDownloadSession.open_arrow_reader`.

    :Example:

    .. code-block:: python

        from odps.tunnel import TableTunnel

            tunnel = TableTunnel(o)
            download_session = tunnel.create_download_session('my_table', partition_spec='pt=test')

            # create a TunnelArrowReader
            with download_session.open_arrow_reader(0, download_session.count) as reader:
                for batch in reader:
                    print(batch.to_pandas())
    """

    def __init__(
        self,
        schema,
        stream_creator,
        columns=None,
        partition_spec=None,
        append_partitions=False,
        use_ipc_stream=False,
    ):
        if pa is None:
            raise ValueError("To use arrow reader you need to install pyarrow")

        self._raw_schema = schema

        raw_arrow_schema = odps_schema_to_arrow_schema(schema)
        if columns is None:
            self._schema = schema
            self._arrow_schema = self._raw_arrow_schema = raw_arrow_schema
        else:
            self._schema = types.OdpsSchema([schema[c] for c in columns])
            self._raw_arrow_schema = pa.schema(
                [s for s in raw_arrow_schema if s.name in columns]
            )
            self._arrow_schema = odps_schema_to_arrow_schema(self._schema)
        self._columns = columns

        self._append_partitions = append_partitions
        self._partition_spec = partition_spec

        self._pos = 0
        self._stream_creator = stream_creator
        self._use_ipc_stream = use_ipc_stream
        self._reopen_reader()

        self._to_datetime = utils.MillisecondsConverter().from_milliseconds
        self._read_limit = options.table_read_limit

        self.closed = False

        self._pd_column_converters = dict()
        # True if need to convert numeric columns with None as float types
        self._coerce_numpy_columns = set()
        for col in schema.simple_columns:
            arrow_type = self._arrow_schema.field(
                self._arrow_schema.get_field_index(col.name)
            ).type
            if isinstance(col.type, (types.Map, types.Array, types.Struct)):
                self._pd_column_converters[col.name] = ArrowRecordFieldConverter(
                    col.type, convert_ts=False
                )
            elif options.tunnel.pd_cast_mode == "numpy" and (
                pa.types.is_integer(arrow_type) or pa.types.is_floating(arrow_type)
            ):
                self._coerce_numpy_columns.add(col.name)

        self._injected_error = None

    def _reopen_reader(self):
        self._last_n_bytes = len(self._reader) if self._pos != 0 else 0
        input_stream = self._stream_creator(self._pos)
        self._arrow_stream = None
        if self._use_ipc_stream:
            self._reader = input_stream
        else:
            self._reader = ArrowStreamReader(input_stream, self._raw_arrow_schema)

    def _inject_error(self, cursor, exc):
        self._injected_error = (cursor, exc)

    @property
    def schema(self):
        return self._schema

    def _read_next_raw_batch(self):
        if self._injected_error is not None and self._injected_error[0] <= self._pos:
            self._injected_error = None
            raise self._injected_error[1]

        if self._arrow_stream is None:
            self._arrow_stream = pa.ipc.open_stream(self._reader)

        if self._read_limit is not None and self._pos >= self._read_limit:
            warnings.warn(
                "Number of lines read via tunnel already reaches the limitation.",
                RuntimeWarning,
            )
            return None

        try:
            batch = self._arrow_stream.read_next_batch()
            self._pos += batch.num_rows
        except pa.ArrowTypeError as ex:
            if str(ex) != "Did not pass numpy.dtype object":
                raise
            else:
                raise pa.ArrowTypeError(
                    "Error caused by version mismatch. Try install numpy<1.20 or "
                    "upgrade your pyarrow version. Original message: " + str(ex)
                )
        except StopIteration:
            return None
        return batch

    def _convert_timezone(self, batch):
        from ...lib import tzlocal

        if not any(isinstance(tp, pa.TimestampType) for tp in batch.schema.types):
            return batch

        timezone = raw_timezone = options.local_timezone
        if timezone is True or timezone is None:
            timezone = str(tzlocal.get_localzone())

        cols = []
        for idx in range(batch.num_columns):
            col = batch.column(idx)
            name = batch.schema.names[idx]
            if not isinstance(col.type, pa.TimestampType):
                cols.append(col)
                continue

            if timezone is False or self._schema[name].type == types.timestamp_ntz:
                col = col.cast(pa.timestamp(col.type.unit))
            else:
                col = col.cast(pa.timestamp(col.type.unit, timezone))
                if raw_timezone is None or raw_timezone is True:
                    if hasattr(pac, "local_timestamp"):
                        col = pac.local_timestamp(col)
                    else:
                        col = pa.Array.from_pandas(
                            col.to_pandas().dt.tz_localize(None)
                        ).cast(pa.timestamp(col.type.unit))
            cols.append(col)

        return pa.RecordBatch.from_arrays(cols, names=batch.schema.names)

    def _append_partition_cols(self, batch):
        col_set = set(self._columns or [c.name for c in self._schema.columns])
        pt_obj = (
            types.PartitionSpec(self._partition_spec) if self._partition_spec else None
        )

        sel_col_set = set(self._columns or [])
        if pt_obj and any(c in sel_col_set for c in pt_obj.keys()):
            # append partitions selected in columns argument
            self._append_partitions = True
        if not pt_obj or not self._append_partitions:
            return batch

        batch_cols = list(batch.columns)
        batch_col_names = list(batch.schema.names)
        for key, val in pt_obj.items():
            if key not in col_set:
                continue
            val = types.validate_value(val, self._schema[key].type)
            batch_cols.append(pa.array(np.repeat([val], batch.num_rows)))
            batch_col_names.append(key)
        return pa.RecordBatch.from_arrays(batch_cols, names=batch_col_names)

    def read_next_batch(self):
        """
        Read next Arrow RecordBatch from tunnel.

        :return: Arrow RecordBatch
        """
        if self._reader is None:
            return None

        batch = utils.call_with_retry(
            self._read_next_raw_batch, reset_func=self._reopen_reader
        )
        if batch is None:
            return None

        batch = self._append_partition_cols(batch)
        if self._columns and self._columns != batch.schema.names:
            col_to_array = dict()
            col_name_set = set(self._columns)
            for name, arr in zip(batch.schema.names, batch.columns):
                if name not in col_name_set:
                    continue
                col_to_array[name] = arr
            arrays = [col_to_array[name] for name in self._columns]
            batch = pa.RecordBatch.from_arrays(arrays, names=self._columns)
        batch = self._convert_timezone(batch)
        return batch

    def read(self):
        """
        Read all data from tunnel and forms an Arrow Table.

        :return: Arrow Table
        """
        batches = []
        while True:
            batch = self.read_next_batch()
            if batch is None:
                break
            batches.append(batch)

        if not batches:
            return self._arrow_schema.empty_table()
        return pa.Table.from_batches(batches)

    def __iter__(self):
        return self

    def __next__(self):
        """
        Read next Arrow RecordBatch from tunnel.
        """
        batch = self.read_next_batch()
        if batch is None:
            raise StopIteration
        return batch

    @property
    def count(self):
        return self._pos

    @property
    def n_bytes(self):
        return self._last_n_bytes + len(self._reader)

    def get_total_bytes(self):
        return self.n_bytes

    def close(self):
        if hasattr(self._reader, "close"):
            self._reader.close()

    def _convert_batch_to_pandas(self, batch):
        series_list = []
        type_mapper = pd.ArrowDtype if options.tunnel.pd_cast_mode == "arrow" else None
        if not self._pd_column_converters and not self._coerce_numpy_columns:
            return batch.to_pandas(types_mapper=type_mapper)
        for col_name, arrow_column in zip(batch.schema.names, batch.columns):
            if col_name not in self._pd_column_converters:
                series = arrow_column.to_pandas(types_mapper=type_mapper)
                if col_name in self._coerce_numpy_columns and series.dtype == np.dtype(
                    "O"
                ):
                    if pa.types.is_floating(arrow_column.type):
                        col_dtype = arrow_column.type.to_pandas_dtype()
                    else:
                        col_dtype = np.dtype(float)
                    series = series.astype(col_dtype)
                series_list.append(series)
            else:
                try:
                    series = arrow_column.to_pandas(types_mapper=type_mapper)
                except pa.ArrowNotImplementedError:
                    dtype = type_mapper(arrow_column.type) if type_mapper else None
                    series = pd.Series(
                        arrow_column.to_pylist(), name=col_name, dtype=dtype
                    )
                series_list.append(series.map(self._pd_column_converters[col_name]))
        return pd.concat(series_list, axis=1)

    def to_pandas(self):
        """
        Read all data from tunnel and convert to a Pandas DataFrame.
        """
        import pandas as pd

        batches = []
        while True:
            batch = self.read_next_batch()
            if batch is None:
                break
            batches.append(self._convert_batch_to_pandas(batch))

        if not batches:
            return self._arrow_schema.empty_table().to_pandas()
        return pd.concat(batches, axis=0, ignore_index=True)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


_reflective = lambda x: x


if convert_legacy_decimal_bytes is None:

    def convert_legacy_decimal_bytes(value):
        """
        Legacy decimal memory layout:
            int8_t  mNull;
            int8_t  mSign;
            int8_t  mIntg;
            int8_t  mFrac; only 0, 1, 2
            int32_t mData[6];
            int8_t mPadding[4]; //For Memory Align
        """
        if value is None:
            return None

        is_null, sign, intg, frac = struct.unpack("<4b", value[:4])
        if is_null:  # pragma: no cover
            return None
        if intg + frac == 0:
            return Decimal("0")

        sio = BytesIO() if compat.PY27 else StringIO()
        if sign > 0:
            sio.write("-")
        intg_nums = struct.unpack("<%dI" % intg, value[12 : 12 + intg * 4])
        intg_val = "".join("%09d" % d for d in reversed(intg_nums)).lstrip("0")
        sio.write(intg_val or "0")
        if frac > 0:
            sio.write(".")
            frac_nums = struct.unpack("<%dI" % frac, value[12 - frac * 4 : 12])
            sio.write("".join("%09d" % d for d in reversed(frac_nums)))
        return Decimal(sio.getvalue())


class ArrowRecordFieldConverter(object):
    _sensitive_types = (
        types.Datetime,
        types.Timestamp,
        types.TimestampNTZ,
        types.Array,
        types.Map,
        types.Struct,
    )

    def __init__(self, odps_type, arrow_type=None, convert_ts=True):
        self._mills_converter = utils.MillisecondsConverter()
        self._mills_converter_utc = utils.MillisecondsConverter(local_tz=False)
        self._convert_ts = convert_ts

        self._converter = self._build_converter(odps_type, arrow_type)

    def _convert_datetime(self, value):
        if value is None:
            return None
        mills = self._mills_converter.to_milliseconds(value)
        return self._mills_converter.from_milliseconds(mills)

    def _convert_ts_timestamp(self, value, ntz=False):
        if value is None:
            return None

        if not ntz:
            converter = self._mills_converter
        else:  # TimestampNtz
            converter = self._mills_converter_utc

        microsec = value.microsecond
        nanosec = value.nanosecond
        secs = int(converter.to_milliseconds(value.to_pydatetime()) / 1000)
        value = pd.Timestamp(converter.from_milliseconds(secs * 1000))
        return value.replace(microsecond=microsec, nanosecond=nanosec)

    def _convert_struct_timestamp(self, value, ntz=False):
        if value is None:
            return None

        if not ntz:
            converter = self._mills_converter
        else:  # TimestampNtz
            converter = self._mills_converter_utc

        ts = pd.Timestamp(converter.from_milliseconds(value["sec"] * 1000))
        nanos = value["nano"]
        return ts.replace(microsecond=nanos // 1000, nanosecond=nanos % 1000)

    @staticmethod
    def _convert_struct_timedelta(value):
        if value is None:
            return None

        nanos = value["nano"]
        return pd.Timedelta(
            seconds=value["sec"], microseconds=nanos // 1000, nanoseconds=nanos % 1000
        )

    @staticmethod
    def _convert_struct(value, field_converters, tuple_type, use_ordered_dict=False):
        if value is None:
            return None

        result_iter = ((k, field_converters[k](v)) for k, v in value.items())
        if tuple_type is not None:
            return tuple_type(**dict(result_iter))
        elif not use_ordered_dict:
            return dict(result_iter)
        else:
            d = dict(result_iter)
            return OrderedDict([(k, d[k]) for k in field_converters if k in d])

    def _build_converter(self, odps_type, arrow_type=None):
        import pyarrow as pa

        arrow_decimal_types = (pa.Decimal128Type,)
        if hasattr(pa, "Decimal256Type"):
            arrow_decimal_types += (pa.Decimal256Type,)

        if self._convert_ts and isinstance(odps_type, types.Datetime):
            return self._convert_datetime
        elif isinstance(odps_type, types.Timestamp):
            if isinstance(arrow_type, pa.StructType):
                return self._convert_struct_timestamp
            elif self._convert_ts:
                return self._convert_ts_timestamp
            else:
                return _reflective
        elif isinstance(odps_type, types.TimestampNTZ):
            if isinstance(arrow_type, pa.StructType):
                return functools.partial(self._convert_struct_timestamp, ntz=True)
            elif self._convert_ts:
                return functools.partial(self._convert_ts_timestamp, ntz=True)
            else:
                return _reflective
        elif (
            isinstance(odps_type, types.Decimal)
            and isinstance(arrow_type, pa.FixedSizeBinaryType)
            and not isinstance(arrow_type, arrow_decimal_types)
        ):
            return convert_legacy_decimal_bytes
        elif isinstance(odps_type, types.IntervalDayTime) and isinstance(
            arrow_type, pa.StructType
        ):
            return self._convert_struct_timedelta
        elif isinstance(odps_type, types.Array):
            arrow_value_type = getattr(arrow_type, "value_type", None)
            sub_converter = self._build_converter(
                odps_type.value_type, arrow_value_type
            )
            if sub_converter is _reflective:
                return _reflective
            return (
                lambda value: [sub_converter(x) for x in value]
                if value is not None
                else None
            )
        elif isinstance(odps_type, types.Map):
            arrow_key_type = getattr(arrow_type, "key_type", None)
            arrow_value_type = getattr(arrow_type, "item_type", None)

            key_converter = self._build_converter(odps_type.key_type, arrow_key_type)
            value_converter = self._build_converter(
                odps_type.value_type, arrow_value_type
            )
            dict_hook = OrderedDict if odps_type._use_ordered_dict else dict
            if key_converter is _reflective and value_converter is _reflective:
                return dict_hook

            return (
                lambda value: dict_hook(
                    [(key_converter(k), value_converter(v)) for k, v in value]
                )
                if value is not None
                else None
            )
        elif isinstance(odps_type, types.Struct):
            field_converters = OrderedDict()
            for field_name, field_type in odps_type.field_types.items():
                arrow_field_type = None
                if arrow_type is not None:
                    arrow_field_type = arrow_type[field_name].type
                field_converters[field_name] = self._build_converter(
                    field_type, arrow_field_type
                )

            if options.struct_as_dict:
                tuple_type = None
            else:
                tuple_type = odps_type.namedtuple_type
            use_ordered_dict = odps_type._use_ordered_dict
            return functools.partial(
                self._convert_struct,
                field_converters=field_converters,
                tuple_type=tuple_type,
                use_ordered_dict=use_ordered_dict,
            )
        else:
            return _reflective

    def __call__(self, value):
        if value is None:
            return None
        return self._converter(value)


class ArrowRecordReader(AbstractRecordReader):
    _complex_types_to_convert = (types.Array, types.Map, types.Struct)

    def __init__(self, arrow_reader, make_compat=True, read_all=False):
        self._arrow_reader = arrow_reader
        self._batch_pos = 0
        self._total_pos = 0
        self._cur_batch = None
        self._make_compat = make_compat

        self._field_converters = None

        if read_all:
            self._cur_batch = arrow_reader.read()

    def _convert_record(self, arrow_values):
        py_values = [x.as_py() for x in arrow_values]
        if not self._make_compat:
            return py_values
        else:
            return [
                converter(value)
                for value, converter in zip(py_values, self._field_converters)
            ]

    def read(self):
        if self._cur_batch is None or self._batch_pos >= self._cur_batch.num_rows:
            self._cur_batch = self._arrow_reader.read_next_batch()
            self._batch_pos = 0

            if self._cur_batch is None or self._cur_batch.num_rows == 0:
                return None

        if self._field_converters is None:
            table_schema = self._arrow_reader.schema
            self._field_converters = [
                ArrowRecordFieldConverter(table_schema[col_name].type, arrow_type)
                for col_name, arrow_type in zip(
                    self._cur_batch.schema.names, self._cur_batch.schema.types
                )
            ]
        tp = tuple(col[self._batch_pos] for col in self._cur_batch.columns)
        self._batch_pos += 1
        self._total_pos += 1

        return Record(schema=self.schema, values=self._convert_record(tp))

    def to_pandas(self, start=None, count=None, **kw):
        step = kw.get("step") or 1
        return self._arrow_reader.to_pandas().iloc[start : start + count : step]

    def close(self):
        self._arrow_reader.close()

    def __next__(self):
        rec = self.read()
        if rec is None:
            raise StopIteration
        return rec

    next = __next__

    @property
    def count(self):
        return self._total_pos

    @property
    def schema(self):
        return self._arrow_reader.schema

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
