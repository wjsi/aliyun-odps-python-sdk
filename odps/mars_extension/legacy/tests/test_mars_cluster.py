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

import math
import time
import uuid
from datetime import datetime, date

import pytest
import requests

from .... import DataFrame
from ....config import options
from ....models import TableSchema, Instance
from ....tests.core import tn, odps2_typed_case

try:
    import mars
    from ..core import (  # noqa: F401
        create_mars_cluster,
        to_mars_dataframe,
        persist_mars_dataframe,
    )
except ImportError:
    mars = None
    pytestmark = pytest.mark.skip("mars not installed")


script = """
df = o.to_mars_dataframe('{}', runtime_endpoint='{}').to_pandas()
o.persist_mars_dataframe(df, '{}', unknown_as_string=True, runtime_endpoint='{}')
"""


def _gen_data():
    return [
        ("hello \x00\x00 world", 2 ** 63 - 1, math.pi, True),
        ("goodbye", 222222, math.e, False),
        ("c" * 300, -(2 ** 63) + 1, -2.222, True),
        ("c" * 20, -(2 ** 11) + 1, 2.222, True),
    ]


def _create_table(odps, table_name):
    fields = ["id", "int_num", "float_num", "bool"]
    types = ["string", "bigint", "double", "boolean"]

    odps.delete_table(table_name, if_exists=True)
    return odps.create_table(
        table_name,
        schema=TableSchema.from_lists(fields, types),
        stored_as="aliorc",
        lifecycle=1,
    )


@pytest.fixture(autouse=True)
def setup(odps):
    from cupid.config import options as cupid_options

    options.verbose = True
    cupid_options.cupid.runtime.endpoint = odps.endpoint


def test_create_mars_cluster(odps):
    import pandas as pd

    mars_source_table_name = tn("mars_datasource")
    mars_des_table_name = tn("mars_datastore")
    _create_table(odps, mars_source_table_name)
    odps.delete_table(mars_des_table_name, if_exists=True)
    data = _gen_data()
    odps.write_table(mars_source_table_name, data)

    client = odps.create_mars_cluster(1, 4, 8, name=str(uuid.uuid4()))
    try:
        assert client._with_notebook is False

        df = odps.to_mars_dataframe(
            mars_source_table_name, runtime_endpoint=odps.endpoint
        )
        df_head = df.head(2)
        odps.persist_mars_dataframe(
            df_head,
            mars_des_table_name,
            unknown_as_string=True,
            runtime_endpoint=odps.endpoint,
        )

        des = odps.to_mars_dataframe(
            mars_des_table_name, runtime_endpoint=odps.endpoint
        )

        expected = odps.get_table(mars_source_table_name).to_df().to_pandas()
        result = des.to_pandas()
        pd.testing.assert_frame_equal(expected.head(2), result)
        odps.delete_table(mars_source_table_name)
        odps.delete_table(mars_des_table_name)
    finally:
        client.stop_server()


def test_mars_dataframe(odps):
    import pandas as pd
    import numpy as np

    client = odps.create_mars_cluster(
        3, 4, 8, name=str(uuid.uuid4()), with_notebook=True
    )
    try:
        assert client._with_notebook is True
        status_code = requests.get(client.notebook_endpoint).status_code
        assert status_code == 200

        mars_source_table_name = tn("mars_df")

        data = pd.DataFrame(
            {"c1": np.random.rand(100), "c2": np.random.randint(0, 100, (100,))}
        )
        odps.delete_table(mars_source_table_name, if_exists=True)
        odps.create_table(
            mars_source_table_name,
            "c1 double, c2 int",
            stored_as="aliorc",
            lifecycle=1,
        )
        DataFrame(data).persist(mars_source_table_name, odps=odps)

        df = odps.to_mars_dataframe(
            mars_source_table_name, runtime_endpoint=odps.endpoint
        )
        result = df.describe().to_pandas()
        expected = data.describe()

        pd.testing.assert_frame_equal(expected, result)
        odps.delete_table(mars_source_table_name)
    finally:
        client.stop_server()


def test_mars_knn(odps):
    client = odps.create_mars_cluster(
        1, 4, 8, name=str(uuid.uuid4()), scheduler_mem=12, scheduler_cpu=4
    )

    try:
        import numpy as np
        import mars.tensor as mt
        from mars.learn.neighbors import NearestNeighbors
        from sklearn.neighbors import NearestNeighbors as SkNearestNeighbors

        rs = np.random.RandomState(0)
        raw_X = rs.rand(10, 5)
        raw_Y = rs.rand(8, 5)

        X = mt.tensor(raw_X, chunk_size=7)
        Y = mt.tensor(raw_Y, chunk_size=(5, 3))

        nn = NearestNeighbors(n_neighbors=3)
        nn.fit(X)
        ret = nn.kneighbors(Y)

        snn = SkNearestNeighbors(n_neighbors=3)
        snn.fit(raw_X)

        expected = snn.kneighbors(raw_Y)
        result = [r.fetch() for r in ret]
        np.testing.assert_almost_equal(result[0], expected[0])
        np.testing.assert_almost_equal(result[1], expected[1])
    finally:
        client.stop_server()


def test_extended(odps):
    def func():
        import lightgbm  # noqa: F401
        import xgboost  # noqa: F401
        import mars.tensor as mt
        from mars.learn.contrib.lightgbm import LGBMClassifier

        n_rows = 1000
        n_columns = 10
        chunk_size = 50
        rs = mt.random.RandomState(0)
        X = rs.rand(n_rows, n_columns, chunk_size=chunk_size)
        y = rs.rand(n_rows, chunk_size=chunk_size)
        y = (y * 10).astype(mt.int32)
        classifier = LGBMClassifier(n_estimators=2)
        classifier.fit(X, y, eval_set=[(X, y)])
        _prediction = classifier.predict(X)  # noqa: F841

    odps.run_mars_job(func, image="extended")


def test_roc_curve(odps):
    import numpy as np
    import pandas as pd
    import mars.dataframe as md
    from mars.learn.metrics import roc_curve, auc
    from sklearn.metrics import roc_curve as sklearn_roc_curve, auc as sklearn_auc

    client = odps.create_mars_cluster(1, 4, 8, name=str(uuid.uuid4()))
    try:
        rs = np.random.RandomState(0)
        raw = pd.DataFrame({"a": rs.randint(0, 10, (10,)), "b": rs.rand(10)})

        df = md.DataFrame(raw)
        y = df["a"].to_tensor().astype("int")
        pred = df["b"].to_tensor().astype("float")
        fpr, tpr, thresholds = roc_curve(y, pred, pos_label=2)
        m = auc(fpr, tpr)

        sk_fpr, sk_tpr, sk_threshod = sklearn_roc_curve(
            raw["a"].to_numpy().astype("int"),
            raw["b"].to_numpy().astype("float"),
            pos_label=2,
        )
        expect_m = sklearn_auc(sk_fpr, sk_tpr)
        assert pytest.approx(m.fetch()) == expect_m
    finally:
        client.stop_server()


def test_run_script(odps):
    import pandas as pd
    from io import BytesIO
    from ....utils import to_binary

    client = odps.create_mars_cluster(1, 4, 8, name=str(uuid.uuid4()))
    try:
        mars_source_table_name = tn("mars_script_datasource")
        mars_des_table_name = tn("mars_script_datastore")
        _create_table(odps, mars_source_table_name)
        odps.delete_table(mars_des_table_name, if_exists=True)
        data = _gen_data()
        odps.write_table(mars_source_table_name, data)

        code = BytesIO(
            to_binary(
                script.format(
                    mars_source_table_name,
                    odps.endpoint,
                    mars_des_table_name,
                    odps.endpoint,
                )
            )
        )

        odps.run_script_in_mars(code, runtime_endpoint=odps.endpoint)
        result = odps.get_table(mars_des_table_name).to_df().to_pandas()
        expected = odps.get_table(mars_source_table_name).to_df().to_pandas()
        pd.testing.assert_frame_equal(result, expected)
    finally:
        client.stop_server()


def test_run_mars_job(odps):
    import pandas as pd

    odps_entry = odps
    mars_source_table_name = tn("mars_script_datasource")
    mars_des_table_name = tn("mars_script_datastore")
    _create_table(odps, mars_source_table_name)
    odps.delete_table(mars_des_table_name, if_exists=True)
    data = _gen_data()
    odps.write_table(mars_source_table_name, data)

    def func(s_name, d_name):
        df = odps_entry.to_mars_dataframe(
            s_name, runtime_endpoint=odps_entry.endpoint
        ).to_pandas()
        odps_entry.persist_mars_dataframe(
            df, d_name, unknown_as_string=True, runtime_endpoint=odps_entry.endpoint
        )

    odps.run_mars_job(
        func,
        args=(mars_source_table_name, mars_des_table_name),
        name=str(uuid.uuid4()),
        worker_cpu=4,
        worker_mem=8,
    )

    result = odps.get_table(mars_des_table_name).to_df().to_pandas()
    expected = odps.get_table(mars_source_table_name).to_df().to_pandas()
    pd.testing.assert_frame_equal(result, expected)


def test_remote(odps):
    import mars.remote as mr

    def add_one(x):
        return x + 1

    def sum_all(xs):
        return sum(xs)

    x_list = []
    for i in range(10):
        x_list.append(mr.spawn(add_one, args=(i,)))

    client = odps.create_mars_cluster(1, 4, 8, name=str(uuid.uuid4()))
    try:
        r = mr.spawn(sum_all, args=(x_list,)).execute().fetch()
        assert r == 55
    finally:
        client.stop_server()


def test_empty_table(odps):
    mars_source_table_name = tn("mars_empty_datasource")
    odps.delete_table(mars_source_table_name, if_exists=True)
    odps.create_table(mars_source_table_name, schema="col1 int, col2 string")

    client = odps.create_mars_cluster(1, 4, 8, name=str(uuid.uuid4()))
    try:
        df = odps.to_mars_dataframe(
            mars_source_table_name, runtime_endpoint=odps.endpoint
        )
        result = df.execute().to_pandas()
        assert list(result.columns) == ["col1", "col2"]
    finally:
        client.stop_server()


def test_view_table(odps):
    import pandas as pd

    mars_source_table_name = tn("mars_view_datasource")
    odps.delete_table(mars_source_table_name, if_exists=True)
    odps.create_table(mars_source_table_name, schema="col1 int, col2 string")
    odps.write_table(mars_source_table_name, [[1, "test1"], [2, "test2"]])

    mars_view_table_name = tn("mars_view_table")
    odps.execute_sql("DROP VIEW IF EXISTS {}".format(mars_view_table_name))
    sql = "create view {} (view_col1, view_col2) as select * from {}".format(
        mars_view_table_name, mars_source_table_name
    )
    odps.execute_sql(sql)

    client = odps.create_mars_cluster(1, 4, 8, name=str(uuid.uuid4()))
    try:
        df = odps.to_mars_dataframe(
            mars_view_table_name, runtime_endpoint=odps.endpoint
        )
        result = df.execute().to_pandas()
        expected = pd.DataFrame(
            {"view_col1": [1, 2], "view_col2": ["test1", "test2"]}
        )
        pd.testing.assert_frame_equal(result, expected)
    finally:
        client.stop_server()


def test_cluster_timeout(odps):
    client = odps.create_mars_cluster(
        1, 4, 8, name=str(uuid.uuid4()), instance_idle_timeout=15
    )
    try:
        assert client._kube_instance.status == Instance.Status.RUNNING
        time.sleep(60)
        assert client._kube_instance.status == Instance.Status.TERMINATED
    finally:
        if client._kube_instance.status != Instance.Status.TERMINATED:
            client.stop_server()


@odps2_typed_case
def test_persist_odps2_types(odps):
    import pandas as pd
    import mars.remote as mr

    mars_source_table_name = tn("mars_odps2_datasource")
    mars_des_table_name = tn("mars_odps2_datastore")
    odps.delete_table(mars_source_table_name, if_exists=True)
    odps.delete_table(mars_des_table_name, if_exists=True)

    table = odps.create_table(
        mars_source_table_name,
        "col1 int, "
        "col2 tinyint,"
        "col3 smallint,"
        "col4 float,"
        "col5 timestamp,"
        "col6 datetime,"
        "col7 date",
        lifecycle=1,
        stored_as="aliorc",
    )

    contents = [
        [
            0,
            1,
            2,
            1.0,
            pd.Timestamp("1998-02-15 23:59:21.943829154"),
            datetime.today(),
            date.today(),
        ],
        [
            0,
            1,
            2,
            1.0,
            pd.Timestamp("1998-02-15 23:59:21.943829154"),
            datetime.today(),
            date.today(),
        ],
        [
            0,
            1,
            2,
            1.0,
            pd.Timestamp("1998-02-15 23:59:21.943829154"),
            datetime.today(),
            date.today(),
        ],
    ]
    odps.write_table(table, contents)

    client = odps.create_mars_cluster(1, 4, 8, name=str(uuid.uuid4()))

    try:
        df = odps.to_mars_dataframe(
            mars_source_table_name, runtime_endpoint=odps.endpoint
        )
        df_head = df.head(2)
        odps.persist_mars_dataframe(
            df_head,
            mars_des_table_name,
            unknown_as_string=True,
            runtime_endpoint=odps.endpoint,
        )

        # test write in remote function
        odps_entry = odps
        mars_des_table_name = tn("mars_odps2_datastore_remote")
        odps.delete_table(mars_des_table_name, if_exists=True)

        def func(d_name):
            import pandas as pd

            contents = [
                [
                    0,
                    1,
                    2,
                    1.0,
                    pd.Timestamp("1998-02-15 23:59:21.943829154"),
                    datetime.today(),
                    date.today(),
                ],
                [
                    0,
                    1,
                    2,
                    1.0,
                    pd.Timestamp("1998-02-15 23:59:21.943829154"),
                    datetime.today(),
                    date.today(),
                ],
                [
                    0,
                    1,
                    2,
                    1.0,
                    pd.Timestamp("1998-02-15 23:59:21.943829154"),
                    datetime.today(),
                    date.today(),
                ],
            ]
            df = pd.DataFrame(
                contents, columns=["col" + str(i + 1) for i in range(7)]
            )
            odps_entry.persist_mars_dataframe(
                df,
                d_name,
                unknown_as_string=True,
                runtime_endpoint=odps_entry.endpoint,
            )

        mr.spawn(func, args=(mars_des_table_name,)).execute()

    finally:
        client.stop_server()


def test_sql_to_dataframe(odps):
    import pandas as pd

    mars_source_table_name = tn("mars_sql_datasource")
    _create_table(odps, mars_source_table_name)
    data = _gen_data()
    odps.write_table(mars_source_table_name, data)

    client = odps.create_mars_cluster(2, 4, 8, name=str(uuid.uuid4()))
    try:
        sql = "select count(1) as count from {}".format(mars_source_table_name)
        df = odps.sql_to_mars_dataframe(sql)
        r = df.execute().to_pandas()
        pd.testing.assert_frame_equal(r, pd.DataFrame([4], columns=["count"]))

        sql = """
        SELECT
        t1.`id`,
        MAX(t1.`int_num`) AS `int_num_max`,
        MAX(t1.`float_num`) AS `float_num_max`
        FROM cupid_test_release.`{}` t1
        GROUP BY
        t1.`id`
        """.format(
            mars_source_table_name
        )
        df2 = odps.sql_to_mars_dataframe(sql)
        r2 = df2.execute().to_pandas()
        expected = odps.execute_sql(sql).open_reader().to_pandas()
        pd.testing.assert_frame_equal(r2, expected)

    finally:
        client.stop_server()


def test_full_partitioned_table(odps):
    import pandas as pd

    mars_source_table_name = tn("mars_cupid_datasource_mpart")
    odps.delete_table(mars_source_table_name, if_exists=True)
    table = odps.create_table(
        mars_source_table_name,
        schema=("col1 int, col2 string", "pt1 string, pt2 string"),
        lifecycle=1,
    )
    for pid in range(5):
        pt = table.create_partition("pt1=test_part%d,pt2=test_part%d" % (pid, pid))
        with pt.open_writer() as writer:
            writer.write([[1 + pid * 2, "test1"], [2 + pid * 2, "test2"]])

    client = odps.create_mars_cluster(1, 4, 8, name=str(uuid.uuid4()))
    try:
        df = odps.to_mars_dataframe(
            mars_source_table_name,
            runtime_endpoint=odps.endpoint,
            append_partitions=True,
            add_offset=True,
        )
        result = df.execute().to_pandas()
        expected = table.to_df().to_pandas()
        pd.testing.assert_frame_equal(result, expected)
    finally:
        client.stop_server()


def test_arrow_tunnel(odps):
    import pandas as pd
    import numpy as np
    import mars.dataframe as md

    mars_source_table_name = tn("mars_arrow_tunnel_datasource")
    mars_des_table_name = tn("mars_arrow_tunnel_datastore")
    odps.delete_table(mars_des_table_name, if_exists=True)
    odps.delete_table(mars_source_table_name, if_exists=True)
    odps.create_table(
        mars_source_table_name, schema="col1 int, col2 string", lifecycle=1
    )
    odps.write_table(mars_source_table_name, [[1, "test1"], [2, "test2"]])

    r = odps.to_mars_dataframe(mars_source_table_name).execute().to_pandas()
    expected = odps.get_table(mars_source_table_name).to_df().to_pandas()
    pd.testing.assert_frame_equal(r, expected)

    data = pd.DataFrame(
        {
            "col1": np.random.rand(
                1000,
            ),
            "col2": np.random.randint(0, 100, (1000,)),
            "col3": np.random.choice(["a", "b", "c"], size=(1000,)),
        }
    )

    df = md.DataFrame(data, chunk_size=300)
    odps.persist_mars_dataframe(
        df, mars_des_table_name, unknown_as_string=True
    )
    expected = odps.get_table(mars_des_table_name).to_df().to_pandas()
    pd.testing.assert_frame_equal(
        expected.sort_values("col1").reset_index(drop=True),
        data.sort_values("col1").reset_index(drop=True),
    )


def test_arrow_tunnel_single_part(odps):
    import pandas as pd
    import numpy as np
    import mars.dataframe as md

    mars_source_table_name = tn("mars_arrow_tunnel_datasource_spart")
    mars_des_table_name = tn("mars_arrow_tunnel_datastore_spart")
    odps.delete_table(mars_des_table_name, if_exists=True)
    odps.delete_table(mars_source_table_name, if_exists=True)
    table = odps.create_table(
        mars_source_table_name,
        schema=("col1 int, col2 string", "pt string"),
        lifecycle=1,
    )
    pt = table.create_partition("pt=test_part")
    with pt.open_writer() as writer:
        writer.write([[1, "test1"], [2, "test2"]])

    r = (
        odps.to_mars_dataframe(
            mars_source_table_name, partition="pt=test_part"
        )
        .execute()
        .to_pandas()
    )
    expected = pt.to_df().to_pandas()
    pd.testing.assert_frame_equal(r, expected)

    data = pd.DataFrame(
        {
            "col1": np.random.rand(
                1000,
            ),
            "col2": np.random.randint(0, 100, (1000,)),
            "col3": np.random.choice(["a", "b", "c"], size=(1000,)),
        }
    )

    df = md.DataFrame(data, chunk_size=300)
    odps.persist_mars_dataframe(
        df, mars_des_table_name, partition="pt=test_part", unknown_as_string=True
    )
    expected = (
        odps.get_table(mars_des_table_name)
        .get_partition("pt=test_part")
        .to_df()
        .to_pandas()
    )
    pd.testing.assert_frame_equal(
        expected.sort_values("col1").reset_index(drop=True),
        data.sort_values("col1").reset_index(drop=True),
    )


def test_arrow_tunnel_multiple_parts(odps):
    import pandas as pd

    mars_source_table_name = tn("mars_arrow_tunnel_datasource_mpart")
    odps.delete_table(mars_source_table_name, if_exists=True)
    table = odps.create_table(
        mars_source_table_name,
        schema=("col1 int, col2 string", "pt string"),
        lifecycle=1,
    )
    for pid in range(5):
        pt = table.create_partition("pt=test_part%d" % pid)
        with pt.open_writer() as writer:
            writer.write([[1 + pid * 2, "test1"], [2 + pid * 2, "test2"]])

    r = (
        odps.to_mars_dataframe(
            mars_source_table_name, append_partitions=True, add_offset=True
        )
        .execute()
        .to_pandas()
    )
    expected = table.to_df().to_pandas()
    pd.testing.assert_frame_equal(r, expected)

    r = (
        odps.to_mars_dataframe(
            mars_source_table_name,
            partition="pt>test_part1",
            append_partitions=True,
            add_offset=True,
        )
        .execute()
        .to_pandas()
    )
    expected = (
        table.to_df().to_pandas().query('pt>"test_part1"').reset_index(drop=True)
    )
    pd.testing.assert_frame_equal(r, expected)


def test_existed_partition(odps):
    import pandas as pd
    import mars.dataframe as md

    mars_source_table_name = tn("mars_existed_partition")
    odps.delete_table(mars_source_table_name, if_exists=True)
    table = odps.create_table(
        mars_source_table_name,
        schema=("col1 int, col2 string", "pt string"),
        lifecycle=1,
    )
    table.create_partition("pt=test")

    df = md.DataFrame(pd.DataFrame({"col1": [1, 2], "col2": list("ab")}))
    odps.persist_mars_dataframe(
        df, mars_source_table_name, partition="pt=test", unknown_as_string=True
    )
