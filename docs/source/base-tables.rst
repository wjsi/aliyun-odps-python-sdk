.. _tables:

表
======

`表 <https://help.aliyun.com/document_detail/27819.html>`_ 是ODPS的数据存储单元。

基本操作
--------

.. note::

    本文档中的代码对 PyODPS 0.11.3 及后续版本有效。对早于 0.11.3 版本的 PyODPS，请使用 ``odps.models.Schema`` 代替
    ``odps.models.TableSchema``，使用 ``schema`` 属性代替 ``table_schema`` 属性。

我们可以用 ODPS 入口对象的 :meth:`~odps.ODPS.list_tables` 来列出项目空间下的所有表。

.. code-block:: python

   for table in o.list_tables():
       print(table.name)

可以通过 ``prefix`` 参数只列举给定前缀的表：

.. code-block:: python

   for table in o.list_tables(prefix="table_prefix"):
       print(table.name)

通过该方法获取的 Table 对象不会自动加载表名以外的属性，此时获取这些属性（例如 ``table_schema`` 或者
``creation_time``）可能导致额外的请求并造成额外的时间开销。如果需要在列举表的同时读取这些属性，在
PyODPS 0.11.5 及后续版本中，可以为 :meth:`~odps.ODPS.list_tables` 添加 ``extended=True`` 参数：

.. code-block:: python

   for table in o.list_tables(extended=True):
       print(table.name, table.creation_time)

如果你需要按类型列举表，可以指定 ``type`` 参数。不同类型的表列举方法如下：

.. code-block:: python

   managed_tables = list(o.list_tables(type="managed_table"))  # 列举内置表
   external_tables = list(o.list_tables(type="external_table"))  # 列举外表
   virtual_views = list(o.list_tables(type="virtual_view"))  # 列举视图
   materialized_views = list(o.list_tables(type="materialized_view"))  # 列举物化视图

通过调用 :meth:`~odps.ODPS.exist_table` 来判断表是否存在。

.. code-block:: python

   o.exist_table('dual')

通过调用 :meth:`~odps.ODPS.get_table` 来获取表。

.. code-block:: python

   >>> t = o.get_table('dual')
   >>> t.table_schema
   odps.Schema {
     c_int_a                 bigint
     c_int_b                 bigint
     c_double_a              double
     c_double_b              double
     c_string_a              string
     c_string_b              string
     c_bool_a                boolean
     c_bool_b                boolean
     c_datetime_a            datetime
     c_datetime_b            datetime
   }
   >>> t.lifecycle
   -1
   >>> print(t.creation_time)
   2014-05-15 14:58:43
   >>> t.is_virtual_view
   False
   >>> t.size
   1408
   >>> t.comment
   'Dual Table Comment'
   >>> t.table_schema.columns
   [<column c_int_a, type bigint>,
    <column c_int_b, type bigint>,
    <column c_double_a, type double>,
    <column c_double_b, type double>,
    <column c_string_a, type string>,
    <column c_string_b, type string>,
    <column c_bool_a, type boolean>,
    <column c_bool_b, type boolean>,
    <column c_datetime_a, type datetime>,
    <column c_datetime_b, type datetime>]
   >>> t.table_schema['c_int_a']
   <column c_int_a, type bigint>
   >>> t.table_schema['c_int_a'].comment
   'Comment of column c_int_a'


通过提供 ``project`` 参数，来跨project获取表。

.. code-block:: python

   >>> t = o.get_table('dual', project='other_project')

创建表
--------

你可以使用\ :ref:`表 schema <table_schema>` 通过 :meth:`~odps.ODPS.create_table` 方法来创建表，方法如下：

.. code-block:: python

   >>> from odps.models import TableSchema, Column, Partition
   >>>
   >>> schema = TableSchema.from_lists(
   >>>    ['num', 'num2', 'arr'], ['bigint', 'double', 'array<int>'], ['pt'], ['string']
   >>> )
   >>> table = o.create_table('my_new_table', schema)
   >>> table = o.create_table('my_new_table', schema, if_not_exists=True)  # 只有不存在表时才创建
   >>> table = o.create_table('my_new_table', schema, lifecycle=7)  # 设置生命周期


更简单的方式是采用“字段名 字段类型”字符串来创建表，方法如下：

.. code-block:: python

   >>> table = o.create_table('my_new_table', 'num bigint, num2 double', if_not_exists=True)
   >>> # 创建分区表可传入 (表字段列表, 分区字段列表)
   >>> table = o.create_table('my_new_table', ('num bigint, num2 double', 'pt string'), if_not_exists=True)


在未经设置的情况下，创建表时，只允许使用 bigint、double、decimal、string、datetime、boolean、map 和 array 类型。\
如果你使用的是位于公共云上的服务，或者支持 tinyint、struct 等新类型，可以设置 ``options.sql.use_odps2_extension = True``
打开这些类型的支持，示例如下：

.. code-block:: python

   >>> from odps import options
   >>> options.sql.use_odps2_extension = True
   >>> table = o.create_table('my_new_table', 'cat smallint, content struct<title:varchar(100), body string>')

:meth:`~odps.ODPS.create_table` 方法也提供了其他参数，可用于设置表属性及事务性等参数。例如，下面的调用创建了一张
ACID 2.0 表并指定 ``key`` 为主键（``key``必须指定为非空）。

.. code-block:: python

   >>> table = o.create_table('my_trans_table', 'key string not null, value string',
   >>>                        primary_key=['key'], transactional=True)


同步表更新
-------------

有时候，一个表可能被别的程序做了更新，比如schema有了变化。此时可以调用 :meth:`~odps.models.Table.reload` 方法来更新。

.. code-block:: python

   >>> table.reload()


读写数据
--------
.. _table_read:

获取表数据
~~~~~~~~~~~

有若干种方法能够获取表数据。首先，如果只是查看每个表的开始的小于1万条数据，则可以使用 :meth:`~odps.models.Table.head` 方法。

.. code-block:: python

   >>> t = o.get_table('dual')
   >>> for record in t.head(3):
   >>>     # 处理每个Record对象


.. _table_open_reader:

其次，在 table 实例上可以执行 :meth:`~odps.models.Table.open_reader` 操作来打一个 reader
来读取数据。如果表为分区表，需要引入 ``partition`` 参数指定需要读取的分区。

使用 with 表达式的写法，with 表达式会保证离开时关闭 reader：

.. code-block:: python

   >>> with t.open_reader(partition='pt=test,pt2=test2') as reader:
   >>>     count = reader.count
   >>>     for record in reader[5:10]:  # 可以执行多次，直到将count数量的record读完，这里可以改造成并行操作
   >>>         # 处理一条记录

不使用 with 表达式的写法：

.. code-block:: python

   >>> reader = t.open_reader(partition='pt=test,pt2=test2')
   >>> count = reader.count
   >>> for record in reader[5:10]:  # 可以执行多次，直到将count数量的record读完，这里可以改造成并行操作
   >>>     # 处理一条记录
   >>> reader.close()

更简单的调用方法是使用 ODPS 对象的 :meth:`~odps.ODPS.read_table` 方法，例如

.. code-block:: python

   >>> for record in o.read_table('test_table', partition='pt=test,pt2=test2'):
   >>>     # 处理一条记录

从 0.11.2 开始，PyODPS 支持使用 `Arrow <https://arrow.apache.org/>`_ 格式读写数据，该格式可以以更高\
效率与 pandas 等格式互相转换。安装 pyarrow 后，在调用 ``open_reader`` 时增加 ``arrow=True`` 参数，即可按
`Arrow RecordBatch <https://arrow.apache.org/docs/python/data.html#record-batches>`_
格式读取表内容。

.. code-block:: python

   >>> with t.open_reader(partition='pt=test,pt2=test2', arrow=True) as reader:
   >>>     count = reader.count
   >>>     for batch in reader:  # 可以执行多次，直到将所有 RecordBatch 读完
   >>>         # 处理一个 RecordBatch，例如转换为 Pandas
   >>>         print(batch.to_pandas())

你也可以直接调用 reader 上的 ``to_pandas`` 方法直接从 reader 获取 pandas DataFrame。
读取时，可以指定起始行号（从0开始）和行数。如果不指定，则默认读取所有数据。

.. code-block:: python

   >>> with t.open_reader(partition='pt=test,pt2=test2', arrow=True) as reader:
   >>>     # 指定起始行号和行数
   >>>     pd_df = reader.to_pandas(start=10, count=20)
   >>>     # 如不指定，则读取所有数据
   >>>     pd_df = reader.to_pandas()

.. _table_to_pandas_mp:

你可以利用多进程加速读取 Pandas DataFrame：

.. code-block:: python

   >>> import multiprocessing
   >>> n_process = multiprocessing.cpu_count()
   >>> with t.open_reader(partition='pt=test,pt2=test2', arrow=True) as reader:
   >>>     pd_df = reader.to_pandas(n_process=n_process)

为方便读取数据为 pandas，从 PyODPS 0.12.0 开始，Table 和 Partition 对象支持直接调用 ``to_pandas``
方法。

.. code-block:: python

   >>> # 将表读取为 pandas DataFrame
   >>> pd_df = table.to_pandas(start=10, count=20)
   >>> # 通过2个进程读取所有数据
   >>> pd_df = table.to_pandas(n_process=2)
   >>> # 将分区读取为 pandas
   >>> pd_df = partitioned_table.to_pandas(partition="pt=test", start=10, count=20)

与此同时，从 PyODPS 0.12.0 开始，你也可以使用 ``iter_pandas`` 方法从一张表或分区按多个批次读取 pandas
DataFrame，并通过 ``batch_size`` 参数指定每次读取的 DataFrame 批次大小，该大小默认值为
``options.tunnel.read_row_batch_size`` 指定，默认为 1024。

.. code-block:: python

    >>> # 以默认 batch_size 读取所有数据
    >>> for batch in table.iter_pandas():
    >>>     print(batch)
    >>> # 以 batch_size==100 读取前 1000 行数据
    >>> for batch in table.iter_pandas(batch_size=100, start=0, count=1000):
    >>>     print(batch)

.. note::

    ``open_reader``、``read_table`` 以及 ``to_pandas`` 方法仅支持读取单个分区。如果需要读取多个分区\
    的值，例如读取所有符合 ``dt>20230119`` 这样条件的分区，需要使用 ``iterate_partitions`` 方法，详见
    :ref:`遍历表分区 <iterate_partitions>` 章节。

导出数据是否包含分区列的值由输出格式决定。Record 格式数据默认包含分区列的值，而 Arrow 格式默认不包含。\
从 PyODPS 0.12.0 开始，你可以通过指定 ``append_partitions=True`` 显示引入分区列的值，通过
``append_partitions=False`` 将分区列排除在结果之外。

.. _table_write:

向表写数据
~~~~~~~~~~

类似于 :meth:`~odps.models.Table.open_reader`，table对象同样能执行 :meth:`~odps.models.Table.open_writer`
来打开writer，并写数据。如果表为分区表，需要引入 ``partition`` 参数指定需要写入的分区。

使用 with 表达式的写法，with 表达式会保证离开时关闭 writer 并提交所有数据：

.. code-block:: python

   >>> with t.open_writer(partition='pt=test') as writer:
   >>>     records = [[111, 'aaa', True],                 # 这里可以是list
   >>>                [222, 'bbb', False],
   >>>                [333, 'ccc', True],
   >>>                [444, '中文', False]]
   >>>     writer.write(records)  # 这里records可以是可迭代对象
   >>>
   >>>     records = [t.new_record([111, 'aaa', True]),   # 也可以是Record对象
   >>>                t.new_record([222, 'bbb', False]),
   >>>                t.new_record([333, 'ccc', True]),
   >>>                t.new_record([444, '中文', False])]
   >>>     writer.write(records)
   >>>


如果分区不存在，可以使用 ``create_partition`` 参数指定创建分区，如

.. code-block:: python

   >>> with t.open_writer(partition='pt=test', create_partition=True) as writer:
   >>>     records = [[111, 'aaa', True],                 # 这里可以是list
   >>>                [222, 'bbb', False],
   >>>                [333, 'ccc', True],
   >>>                [444, '中文', False]]
   >>>     writer.write(records)  # 这里records可以是可迭代对象

更简单的写数据方法是使用 ODPS 对象的 :meth:`~odps.ODPS.write_table` 方法，例如

.. code-block:: python

   >>> records = [[111, 'aaa', True],                 # 这里可以是list
   >>>            [222, 'bbb', False],
   >>>            [333, 'ccc', True],
   >>>            [444, '中文', False]]
   >>> o.write_table('test_table', records, partition='pt=test', create_partition=True)

.. note::

    **注意**\ ：每次调用 :meth:`~odps.ODPS.write_table`，MaxCompute 都会在服务端生成一个文件。\
    这一操作需要较大的时间开销，同时过多的文件会降低后续的查询效率。因此，我们建议在使用
    :meth:`~odps.ODPS.write_table` 方法时，一次性写入多组数据，或者传入一个 generator 对象。

    :meth:`~odps.ODPS.write_table` 写表时会追加到原有数据。如果需要覆盖数据，可以为 :meth:`~odps.ODPS.write_table`
    增加一个参数 ``overwrite=True``（仅在 0.11.1 以后支持），或者调用 :meth:`Table.truncate() <odps.models.Table.truncate>`
    / 删除分区后再建立分区。

你可以使用多线程写入数据。从 PyODPS 0.11.6 开始，直接将 open_writer 创建的 Writer 对象分发到\
各个线程中即可完成多线程写入，写入时请注意不要关闭 writer，待所有数据写入完成后再关闭 writer。

.. code-block:: python

    import random
    # Python 2.7 请从三方库 futures 中 import ThreadPoolExecutor
    from concurrent.futures import ThreadPoolExecutor

    def write_records(writer):
        for i in range(5):
            # 生成数据并写入
            record = table.new_record([random.randint(1, 100), random.random()])
            writer.write(record)

    N_THREADS = 3

    # 此处省略入口对象 o 的创建过程
    table = o.create_table('my_new_table', 'num bigint, num2 double', if_not_exists=True)

    with table.open_writer() as writer:
        pool = ThreadPoolExecutor(N_THREADS)
        futures = []
        for i in range(N_THREADS):
            futures.append(pool.submit(write_records, writer))
        # 等待线程中的写入完成
        [f.result() for f in futures]

你也可以使用多进程写入数据，以避免 Python GIL 带来的性能损失。从 PyODPS 0.11.6 开始，只需要将
open_writer 创建的 Writer 对象通过 multiprocessing 标准库传递到需要写入的子进程中即可写入。\
需要注意的是，与多线程的情形不同，你应当在每个子进程完成写入后关闭 writer，并在所有写入子进程退出后\
再关闭主进程 writer（或离开 with 语句块），以保证所有数据被提交。

.. code-block:: python

    import random
    from multiprocessing import Pool

    def write_records(writer):
        for i in range(5):
            # 生成数据并写入
            record = table.new_record([random.randint(1, 100), random.random()])
            writer.write(record)
        # 需要手动在每个子进程中关闭连接
        writer.close()

    # 如果在独立的 Python 代码文件中，需要判断是否代码按主模块执行
    # 以防止下面的代码被 multiprocessing 反复执行
    if __name__ == '__main__':
        N_WORKERS = 3

        # 此处省略入口对象 o 的创建过程
        table = o.create_table('my_new_table', 'num bigint, num2 double', if_not_exists=True)

        with table.open_writer() as writer:
            pool = Pool(processes=N_WORKERS)
            futures = []
            for i in range(N_WORKERS):
                futures.append(pool.apply_async(write_records, (writer,)))
            # 等待子进程中的执行完成
            [f.get() for f in futures]

从 0.11.2 开始，PyODPS 支持使用 `Arrow <https://arrow.apache.org/>`_ 格式读写数据，该格式可以以更高效率与
pandas 等格式互相转换。安装 pyarrow 后，在调用 ``open_writer`` 时增加 ``arrow=True`` 参数，即可按
`Arrow RecordBatch <https://arrow.apache.org/docs/python/data.html#record-batches>`_
格式写入表内容。PyODPS 也支持直接写入 pandas DataFrame，支持自动转换为 Arrow RecordBatch。

.. code-block:: python

   >>> import pandas as pd
   >>> import pyarrow as pa
   >>>
   >>> with t.open_writer(partition='pt=test', create_partition=True, arrow=True) as writer:
   >>>     records = [[111, 'aaa', True],
   >>>                [222, 'bbb', False],
   >>>                [333, 'ccc', True],
   >>>                [444, '中文', False]]
   >>>     df = pd.DataFrame(records, columns=["int_val", "str_val", "bool_val"])
   >>>     # 写入 RecordBatch
   >>>     batch = pa.RecordBatch.from_pandas(df)
   >>>     writer.write(batch)
   >>>     # 也可以直接写入 Pandas DataFrame
   >>>     writer.write(df)

为方便写入 pandas DataFrame，从 0.12.0 开始，PyODPS 支持直接通过 ``write_table`` 方法写入 pandas DataFrame。\
如果写入数据前对应表不存在，可以增加 ``create_table=True`` 参数以自动创建表。

.. code-block:: python

   >>> import pandas as pd
   >>> df = pd.DataFrame([
   >>>     [111, 'aaa', True],
   >>>     [222, 'bbb', False],
   >>>     [333, 'ccc', True],
   >>>     [444, '中文', False]
   >>> ], columns=['num_col', 'str_col', 'bool_col'])
   >>> # 如果表 test_table 不存在，将会自动创建
   >>> o.write_table('test_table', df, partition='pt=test', create_table=True, create_partition=True)

从 PyODPS 0.12.0 开始，``write_table`` 方法也支持动态分区，可通过 ``partition_cols`` 参数传入需要作为分区的列名，\
并指定 ``create_partition=True``，相应的分区将会自动创建。

.. code-block:: python

   >>> import pandas as pd
   >>> df = pd.DataFrame([
   >>>     [111, 'aaa', True, 'p1'],
   >>>     [222, 'bbb', False, 'p1'],
   >>>     [333, 'ccc', True, 'p2'],
   >>>     [444, '中文', False, 'p2']
   >>> ], columns=['num_col', 'str_col', 'bool_col', 'pt'])
   >>> # 如果分区 pt=p1 或 pt=p2 不存在，将会自动创建。
   >>> o.write_table('test_part_table', df, partition_cols=['pt'], create_partition=True)

.. note::

   ``partition_cols`` 参数从 PyODPS 0.12.3 开始支持。在此之前的版本请使用 ``partitions`` 参数。

压缩选项
~~~~~~~~
为加快数据上传 / 下载速度，你可以在上传 / 下载数据时设置压缩选项。具体地，可以创建一个 ``CompressOption``
实例，在其中指定需要的压缩算法及压缩等级。目前可用的压缩算法包括 zlib 和 ZSTD，其中 ZSTD 需要额外安装
``zstandard`` 包。

.. code-block:: python

   from odps.tunnel import CompressOption

   compress_option = CompressOption(
       compress_algo="zlib",  # 算法名称
       level=0,               # 压缩等级，可选
       strategy=0,            # 压缩策略，可选，目前仅适用于 zlib
   )

此后可在 ``open_reader`` / ``open_writer`` 中设置压缩选项，例如：

.. code-block:: python

   with table.open_writer(compress_option=compress_option) as writer:
       # 写入数据，此处从略

如果仅需指定算法名，也可以直接在 ``open_reader`` / ``open_writer`` 中指定 ``compress_algo`` 参数，例如

.. code-block:: python

   with table.open_writer(compress_algo="zlib") as writer:
       # 写入数据，此处从略

删除表
-------

.. code-block:: python

   >>> o.delete_table('my_table_name', if_exists=True)  #  只有表存在时删除
   >>> t.drop()  # Table对象存在的时候可以直接执行drop函数


创建DataFrame
-----------------

PyODPS提供了 :ref:`DataFrame框架 <df>` ，支持更方便地方式来查询和操作ODPS数据。
使用 ``to_df`` 方法，即可转化为 DataFrame 对象。

.. code-block:: python

   >>> table = o.get_table('my_table_name')
   >>> df = table.to_df()

表分区
-------

基本操作
~~~~~~~~~~~

判断表是否为分区表：

.. code:: python

   >>> if table.table_schema.partitions:
   >>>     print('Table %s is partitioned.' % table.name)

使用 :meth:`~odps.models.Table.exist_partition` 方法判断分区是否存在（该方法需要填写所有分区字段值）：

.. code:: python

   >>> table.exist_partition('pt=test,sub=2015')

判断给定前缀的分区是否存在：

.. code:: python

   >>> # 表 table 的分区字段依次为 pt, sub
   >>> table.exist_partitions('pt=test')

使用 :meth:`~odps.models.Table.get_partition` 方法获取一个分区的相关信息：

.. code:: python

   >>> partition = table.get_partition('pt=test')
   >>> print(partition.creation_time)
   2015-11-18 22:22:27
   >>> partition.size
   0

.. note::

    这里的"分区"指的不是分区字段而是所有分区字段均确定的分区定义对应的子表。如果某个分区字段对应多个值，
    则相应地有多个子表，即多个分区。而 :meth:`~odps.models.Table.get_partition` 只能获取一个分区的信息。因而，

    #. 如果某些分区未指定，那么这个分区定义可能对应多个子表，``get_partition`` 时则不被 PyODPS 支持。\
       此时，需要使用 :meth:`~odps.models.Table.iterate_partitions` 分别处理每个分区。
    #. 如果某个分区字段被定义多次，或者使用类似 ``pt>20210302`` 这样的非确定逻辑表达式，则无法使用
       ``get_partition`` 获取分区。在此情况下，可以尝试使用 ``iterate_partitions`` 枚举每个分区。

创建分区
~~~~~~~~

下面的操作使用 :meth:`~odps.models.Table.create_partition` 方法创建一个分区，如果分区存在将报错：

.. code:: python

   >>> t.create_partition('pt=test')

下面的操作将创建一个分区，如果分区存在则跳过：

.. code:: python

   >>> t.create_partition('pt=test', if_not_exists=True)

.. _iterate_partitions:

遍历表分区
~~~~~~~~
下面的操作将遍历表全部分区：

.. code:: python

   >>> for partition in table.partitions:
   >>>     print(partition.name)

如果要遍历部分分区值确定的分区，可以使用 :meth:`~odps.models.Table.iterate_partitions` 方法。

.. code:: python

   >>> for partition in table.iterate_partitions(spec='pt=test'):
   >>>     print(partition.name)

自 PyODPS 0.11.3 开始，支持为 ``iterate_partitions`` 指定简单的逻辑表达式及通过逗号连接，\
每个子表达式均须满足的复合逻辑表达式。或运算符暂不支持。

.. code:: python

   >>> for partition in table.iterate_partitions(spec='dt>20230119'):
   >>>     print(partition.name)

.. note::

    在 0.11.3 之前的版本中，``iterate_partitions`` 仅支持枚举前若干个分区等于相应值的情形。例如，
    当表的分区字段按顺序分别为 pt1、pt2 和 pt3，那么 ``iterate_partitions`` 中的  ``spec``
    参数只能指定 ``pt1=xxx`` 或者 ``pt1=xxx,pt2=yyy`` 这样的形式。自 0.11.3 开始，
    ``iterate_partitions`` 支持更多枚举方式，但仍建议尽可能限定上一级分区以提高枚举的效率。

删除分区
~~~~~~~~~

下面的操作使用 :meth:`~odps.models.Table.delete_partition` 方法删除一个分区：

.. code:: python

   >>> t.delete_partition('pt=test', if_exists=True)  # 存在的时候才删除
   >>> partition.drop()  # Partition对象存在的时候直接drop

获取值最大分区
~~~~~~~~~~~
很多时候你可能希望获取值最大的分区。例如，当以日期为分区值时，你可能希望获得日期最近的有数据的分区。PyODPS 自 0.11.3
开始支持此功能。

创建分区表并写入一些数据：

.. code-block:: python

    t = o.create_table("test_multi_pt_table", ("col string", "pt1 string, pt2 string"))
    for pt1, pt2 in (("a", "a"), ("a", "b"), ("b", "c"), ("b", "d")):
        o.write_table("test_multi_pt_table", [["value"]], partition="pt1=%s,pt2=%s" % (pt1, pt2))

如果想要获得值最大的分区，可以使用下面的代码：

.. code:: python

    >>> part = t.get_max_partition()
    >>> part
    <Partition cupid_test_release.`test_multi_pt_table`(pt1='b',pt2='d')>
    >>> part.partition_spec["pt1"]  # 获取某个分区字段的值
    b

如果只希望获得最新的分区而忽略分区内是否有数据，可以用

.. code:: python

    >>> t.get_max_partition(skip_empty=False)
    <Partition cupid_test_release.`test_multi_pt_table`(pt1='b',pt2='d')>

对于多级分区表，可以通过限定上级分区值来获得值最大的子分区，例如

.. code:: python

    >>> t.get_max_partition("pt1=a")
    <Partition cupid_test_release.`test_multi_pt_table`(pt1='a',pt2='b')>

.. _tunnel:

数据上传下载通道
----------------
.. note::

    不推荐直接使用 Tunnel 接口，该接口较为低级，简单的表写入推荐直接使用 Tunnel 接口上实现的表
    :ref:`写 <table_write>` 和 :ref:`读 <table_read>` 接口，可靠性和易用性更高。
    只有在分布式写表等复杂场景下有直接使用 Tunnel 接口的需要。

ODPS Tunnel 是 MaxCompute 的数据通道，用户可以通过 Tunnel 向 MaxCompute 中上传或者下载数据。\
关于 ODPS Tunnel 的详细解释可以参考\ `https://help.aliyun.com/zh/maxcompute/user-guide/overview-of-dts <这篇文档>`_。

上传
~~~~~~
分块上传接口
^^^^^^^^^^^^^
直接使用 Tunnel 分块接口上传时，需要首先通过 :meth:`~odps.tunnel.TableTunnel.create_upload_session`
方法使用表名和分区创建 Upload Session，此后从 Upload Session 创建 Writer。每个 Upload Session 可多次调用
:meth:`~odps.tunnel.TableUploadSession.open_record_writer` 方法创建多个 Writer，每个 Writer 拥有一个
``block_id`` 对应一个数据块。写入的数据类型为 :ref:`Record <record-type>` 类型。完成所有写入后，需要调用
Upload Session 上的 :meth:`~odps.tunnel.TableUploadSession.commit` 方法并指定需要提交的数据块列表。\
如果有某个 ``block_id`` 有数据写入但未包括在 ``commit`` 的参数中，则该数据块不会出现在最终的表中。

对于需要写入数据的情形，\ ``commit`` 调用有且只能有一次，完成 ``commit`` 后 Upload Session
即完成写入，此后无法再在该 Upload Session 上提交。

.. code-block:: python

   from odps.tunnel import TableTunnel

   table = o.get_table('my_table')

   tunnel = TableTunnel(o)
   # 为 table 和 pt=test 分区创建 Upload Session
   upload_session = tunnel.create_upload_session(table.name, partition_spec='pt=test')

   # 创建 record writer 并指定需要写入的 block_id 为 0
   with upload_session.open_record_writer(0) as writer:
       record = table.new_record()
       record[0] = 'test1'
       record[1] = 'id1'
       writer.write(record)

       record = table.new_record(['test2', 'id2'])
       writer.write(record)

   # 提交刚才写入的 block 0。多个 block id 需要同时提交
   # 需要在 with 代码块外 commit，否则数据未写入即 commit，会导致报错并丢失已写入的数据
   # 对每个 upload_session，commit 只能调用一次
   upload_session.commit([0])

如果你需要在多个进程乃至节点中使用相同的 Upload Session，可以先创建 Upload Session，并获取其 ``id``
属性。此后在其他进程中调用 ``create_upload_session`` 方法时，将该值作为 ``upload_id`` 参数。\
完成每个进程的上传后，需要收集各进程提交数据所用的 ``block_id``，并在某个进程中完成 ``commit``。

.. code-block:: python

   from odps.tunnel import TableTunnel

   ##############
   # 主进程
   ##############

   table = o.get_table('my_table')

   tunnel = TableTunnel(o)
   # 为 table 和 pt=test 分区创建 Upload Session
   upload_session_main = tunnel.create_upload_session(table.name, partition_spec='pt=test')
   # 获取 Session ID
   session_id = upload_session_main.id

   # 分发 Session ID，此处省略分发过程

   ##############
   # 子进程
   ##############

   # 使用分发的 upload_id 创建 upload session
   upload_session_sub = tunnel.create_upload_session(table.name, partition_spec='pt=test', upload_id=session_id)
   # 创建 reader 并写入数据，注意区分不同进程的 block_id
   with upload_session_sub.open_record_writer(local_block_id) as writer:
       # ... 生成数据 ...
       writer.write(record)

   # 回传本进程中使用的所有 block_id，此处省略回传过程

   ##############
   # 主进程
   ##############

   # 收集所有子进程上的 block_id，此处省略收集过程

   # 提交收集到的 block_id
   upload_session_main.commit(collected_block_ids)

需要注意的是，指定 block id 后，所创建的 Writer 为长连接，如果长时间不写入会导致连接关闭，并导致写入失败，\
该时间通常为 5 分钟。如果你写入数据的间隔较大，建议生成一批数据后再通过 ``open_record_writer`` 接口创建
Writer 并按需写入数据。如果你只希望在单个 Writer 上通过 Tunnel 写入数据，可以考虑在调用 ``open_record_writer``
时不指定 block id，此时创建的 Writer 在写入数据时将首先将数据缓存在本地，当 Writer 关闭或者缓存数据大于\
一定大小（默认为 20MB，可通过 ``options.tunnel.block_buffer_size`` 指定）时才会写入数据。写入数据后，\
需要先通过 Writer 上的 :meth:`~odps.tunnel.BufferedRecordWriter.get_blocks_written`
方法获得已经写入的 block 列表，再进行提交。

.. code-block:: python

   from odps.tunnel import TableTunnel

   table = o.get_table('my_table')

   tunnel = TableTunnel(o)
   # 为 table 和 pt=test 分区创建 Upload Session
   upload_session = tunnel.create_upload_session(table.name, partition_spec='pt=test')

   # 不指定 block id 以创建带缓存的 record writer
   with upload_session.open_record_writer() as writer:
       record = table.new_record()
       record[0] = 'test1'
       record[1] = 'id1'
       writer.write(record)

       record = table.new_record(['test2', 'id2'])
       writer.write(record)

   # 需要在 with 代码块外 commit，否则数据未写入即 commit，会导致报错
   # 从 writer 获得已经写入的 block id 并提交
   upload_session.commit(writer.get_blocks_written())

.. note::

    使用带缓存的 Writer 时，需要注意不能在同一 Upload Session 上开启多个带缓存 Writer 进行写入，\
    否则可能导致冲突而使数据丢失。

如果你需要使用 Arrow 格式而不是 Record 格式进行上传，可以将 :meth:`~odps.tunnel.TableUploadSession.open_record_writer`
替换为 :meth:`~odps.tunnel.TableUploadSession.open_arrow_writer`，并写入 Arrow RecordBatch
/ Arrow Table 或者 pandas DataFrame。

.. code-block:: python

   import pandas as pd
   import pyarrow as pa
   from odps.tunnel import TableTunnel

   table = o.get_table('my_table')

   tunnel = TableTunnel(o)
   upload_session = tunnel.create_upload_session(table.name, partition_spec='pt=test')

   # 使用 open_arrow_writer 而不是 open_record_writer
   with upload_session.open_arrow_writer(0) as writer:
       df = pd.DataFrame({"name": ["test1", "test2"], "id": ["id1", "id2"]})
       batch = pa.RecordBatch.from_pandas(df)
       writer.write(batch)

   # 需要在 with 代码块外 commit，否则数据未写入即 commit，会导致报错
   upload_session.commit([0])

本章节中所述所有 Writer 均非线程安全。你需要为每个线程单独创建 Writer。

流式上传接口
^^^^^^^^^^^^^
MaxCompute 提供了\ `流式上传接口 <https://help.aliyun.com/zh/maxcompute/user-guide/overview-of-streaming-data-channels>`_\
用于简化分布式服务开发成本。可以使用 :meth:`~odps.tunnel.TableTunnel.create_stream_upload_session`
方法创建专门的 Upload Session。此时，不需要为该 Session 的 ``open_record_writer`` 提供 block id。

.. code-block:: python

   from odps.tunnel import TableTunnel

   table = o.get_table('my_table')

   tunnel = TableTunnel(o)
   upload_session = tunnel.create_stream_upload_session(table.name, partition_spec='pt=test')

   with upload_session.open_record_writer() as writer:
       record = table.new_record()
       record[0] = 'test1'
       record[1] = 'id1'
       writer.write(record)

       record = table.new_record(['test2', 'id2'])
       writer.write(record)

下载
~~~~~~

直接使用 Tunnel 接口下载数据时，需要首先使用表名和分区创建 Download Session，此后从 Download Session
创建 Reader。每个 Download Session 可多次调用 :meth:`~odps.tunnel.TableDownloadSession.open_record_reader`
方法创建多个 Reader，每个 Reader 需要指定起始行号以及需要的行数。起始行号从 0 开始，行数可指定为 Session
的 ``count`` 属性，为表或分区的总行数。读取的数据类型为 :ref:`Record <record-type>` 类型。

.. code-block:: python

   from odps.tunnel import TableTunnel

   tunnel = TableTunnel(o)
   # 为 table 和 pt=test 分区创建 Download Session
   download_session = tunnel.create_download_session('my_table', partition_spec='pt=test')

   # 创建 record reader 并指定需要读取的行范围
   with download_session.open_record_reader(0, download_session.count) as reader:
       for record in reader:
           # 处理每条记录

如果你需要在多个进程乃至节点中使用相同的 Download Session，可以先创建 Download Session，并获取其 ``id``
属性。此后在其他进程中调用 :meth:`~odps.tunnel.TableTunnel.create_download_session` 方法时，将该值作为
``download_id`` 参数。

.. code-block:: python

   from odps.tunnel import TableTunnel

   ##############
   # 主进程
   ##############

   table = o.get_table('my_table')

   tunnel = TableTunnel(o)
   # 为 table 和 pt=test 分区创建 Download Session
   download_session_main = tunnel.create_download_session(table.name, partition_spec='pt=test')
   # 获取 Session ID
   session_id = download_session_main.id

   # 分发 Session ID，此处省略分发过程

   ##############
   # 子进程
   ##############

   # 使用分发的 upload_id 创建 download session
   download_session_sub = tunnel.create_download_session(table.name, partition_spec='pt=test', download_id=session_id)
   # 创建 reader 并读取数据，注意不同的进程可能需要指定不同的 start / count
   with download_session_sub.open_record_reader(start, count) as reader:
       for record in reader:
           # 处理记录

你也可以通过使用 :meth:`~odps.tunnel.TableDownloadSession.open_arrow_reader` 而不是
:meth:`~odps.tunnel.TableDownloadSession.open_record_reader` 使读取的数据为 Arrow
格式而不是 Record 格式。

.. code-block:: python

   from odps.tunnel import TableTunnel

   tunnel = TableTunnel(o)
   download_session = tunnel.create_download_session('my_table', partition_spec='pt=test')

   with download_session.open_arrow_reader(0, download_session.count) as reader:
       for batch in reader:
           # 处理每个 Arrow RecordBatch

压缩选项
~~~~~~~~
为加快数据上传 / 下载速度，你可以在上传 / 下载数据时设置压缩选项。具体地，可以创建一个 ``CompressOption``
实例，在其中指定需要的压缩算法及压缩等级。目前可用的压缩算法包括 zlib 和 ZSTD，其中 ZSTD 需要额外安装
``zstandard`` 包。

.. code-block:: python

   from odps.tunnel import CompressOption

   compress_option = CompressOption(
       compress_algo="zlib",  # 算法名称
       level=0,               # 压缩等级，可选
       strategy=0,            # 压缩策略，可选，目前仅适用于 zlib
   )

此后，在创建 Upload / Download Session 时，可以指定 ``compress_option`` 参数，并在 ``open_xxx_reader``
/ ``open_xxx_writer`` 方法中设置 ``compress=True`` 即可启用压缩：

.. code-block:: python

   tunnel = TableTunnel(o)
   # 为 table 和 pt=test 分区创建 Download Session
   download_session = tunnel.create_download_session(
       'my_table', partition_spec='pt=test', compress_option=compress_option
   )

   # 创建 record reader 并指定需要读取的行范围
   with download_session.open_record_reader(0, download_session.count, compress=True) as reader:
       for record in reader:
           # 处理每条记录

自 PyODPS 0.12.3 起，你可以通过全局配置指定当前 Python 进程中使用的压缩选项，示例如下：

.. code-block:: python

   from odps import options

   # 启用压缩（默认为 zlib / deflate 编码）
   options.tunnel.compress.enabled = True
   # 设置压缩算法
   options.tunnel.compress.algo = "zstd"

此后在所有后续数据读写操作中，都会启用压缩。更多压缩选项可以参考\ :ref:`配置选项 <options_tunnel>`。

提升上传和下载性能
~~~~~~~~~~~~~~~~~~~

Tunnel 上传和下载性能受到各种因素影响较大。首先，考虑对本地代码的优化，主要有下面的优化点：

1. 减少创建 Upload Session 或者 Download Session 的次数，尽量复用。Tunnel Session 本身创建代价较大，\
   因而除非必要，一次读取或写入只应当创建一个。
2. 增加每个 Reader / Writer 读取或者写入的数据量。
3. 启用数据压缩以减小传输的数据量。
4. 如果数据源或者需要的数据目标为 pandas，由于 Record 类型本身需要较大的 Python 解释器时间开销，因而建议尽量采用 Arrow
   接口进行读写。
5. 如有可能，使用多线程或者 multiprocessing 进行读写。需要注意的是，Python 使用了 GIL，因而如果你读写数据\
   前的预处理步骤使用了较多纯 Python 代码，那么多线程可能未必提升性能。

此外，读写数据时的网络状况等因素也可能影响上传和下载速度，可能发生共享 Tunnel 服务资源用满或者客户端到 Tunnel
服务网络链路不稳定等因素。针对这些情形，可以考虑购买独享资源 Tunnel 或者使用阿里云内网，相关信息可以\
参考\ `Tunnel 文档 <https://help.aliyun.com/zh/maxcompute/user-guide/overview-of-dts#094b91802f18e>`_。
