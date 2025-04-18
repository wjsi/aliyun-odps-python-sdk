.. _models:

XFlow 和模型
=============

XFlow
------

XFlow 是 ODPS 对算法包的封装，使用 PyODPS 可以执行 XFlow。对于下面的 PAI 命令：

.. code::

    PAI -name AlgoName -project algo_public -Dparam1=param_value1 -Dparam2=param_value2 ...

可以使用 :meth:`~odps.ODPS.run_xflow` 提交任务：

.. code:: python

    >>> # 异步调用
    >>> inst = o.run_xflow('AlgoName', 'algo_public',
                           parameters={'param1': 'param_value1', 'param2': 'param_value2', ...})

或者使用 :meth:`~odps.ODPS.execute_xflow` 提交任务并等待执行完成：

.. code:: python

    >>> # 同步调用
    >>> inst = o.execute_xflow('AlgoName', 'algo_public',
                               parameters={'param1': 'param_value1', 'param2': 'param_value2', ...})

参数不应包含命令两端的引号（如果有），也不应该包含末尾的分号。

这两个方法都会返回一个 :class:`~odps.models.Instance` 对象。由于
XFlow 的一个 Instance 包含若干个子 Instance，需要使用下面的方法来获得每个 Instance 的 LogView：

.. code-block:: python

    >>> for sub_inst_name, sub_inst in o.get_xflow_sub_instances(inst).items():
    >>>     print('%s: %s' % (sub_inst_name, sub_inst.get_logview_address()))

需要注意的是，:meth:`~odps.ODPS.get_xflow_sub_instances` 返回的是 Instance 当前的子 Instance，\
可能会随时间变化，因而可能需要定时查询。为简化这一步骤，可以使用 :meth:`~odps.ODPS.iter_xflow_sub_instances`
方法。该方法返回一个迭代器，会阻塞执行直至发现新的子 Instance 或者主 Instance 结束。同时需要注意的是，
:meth:`~odps.ODPS.iter_xflow_sub_instances` 默认不会检查 Instance 是否报错，建议在循环结束时手动检查
Instance 是否报错，以免遗漏可能的问题，或者增加 ``check=True`` 参数在 :meth:`~odps.ODPS.iter_xflow_sub_instances`
退出时自动检查：

.. code-block:: python

    >>> # 此处建议使用异步调用
    >>> inst = o.run_xflow('AlgoName', 'algo_public',
                           parameters={'param1': 'param_value1', 'param2': 'param_value2', ...})
    >>> # 如果循环中没有 break，该循环会执行到 instance 退出
    >>> for sub_inst_name, sub_inst in o.iter_xflow_sub_instances(inst):
    >>>     print('%s: %s' % (sub_inst_name, sub_inst.get_logview_address()))
    >>> # 手动检查 instance 是否成功，以避免遗漏 instance 报错
    >>> instance.wait_for_success()

或者

.. code-block:: python

    >>> # 此处建议使用异步调用
    >>> inst = o.run_xflow('AlgoName', 'algo_public',
                           parameters={'param1': 'param_value1', 'param2': 'param_value2', ...})
    >>> # 增加 check=True，在循环结束时自动检查报错。如果循环中 break，instance 错误不会被抛出
    >>> for sub_inst_name, sub_inst in o.iter_xflow_sub_instances(inst, check=True):
    >>>     print('%s: %s' % (sub_inst_name, sub_inst.get_logview_address()))

在调用 run_xflow 或者 execute_xflow 时，也可以指定运行参数，指定的方法与 SQL 类似：

.. code-block:: python

    >>> parameters = {'param1': 'param_value1', 'param2': 'param_value2', ...}
    >>> o.execute_xflow('AlgoName', 'algo_public', parameters=parameters, hints={'odps.xxx.yyy': 10})


例如，如果需要任务运行到指定卡型的机器上，可以在 hints 中增加如下配置：

.. code-block:: python

    >>> hints={"settings": json.dumps({"odps.algo.hybrid.deploy.info": "xxxxx"})}


使用 options.ml.xflow_settings 可以配置全局设置：

.. code-block:: python

    >>> from odps import options
    >>> options.ml.xflow_settings = {'odps.xxx.yyy': 10}
    >>> parameters = {'param1': 'param_value1', 'param2': 'param_value2', ...}
    >>> o.execute_xflow('AlgoName', 'algo_public', parameters=parameters)

PAI 命令的文档可以参考 `这份文档 <https://help.aliyun.com/document_detail/114368.html>`_ 里列出的各个"组件参考"章节。

离线模型
---------

离线模型是 XFlow 分类 / 回归算法输出的模型。用户可以使用 PyODPS ML 或直接使用 odps.run_xflow 创建一个离线模型，例如下面使用
run_xflow 的例子：

.. code:: python

    >>> o.run_xflow('LogisticRegression', 'algo_public', dict(modelName='logistic_regression_model_name',
    >>>             regularizedLevel='1', maxIter='100', regularizedType='l1', epsilon='0.000001', labelColName='y',
    >>>             featureColNames='pdays,emp_var_rate', goodValue='1', inputTableName='bank_data'))

在模型创建后，用户可以列出当前 Project 下的模型：

.. code:: python

    >>> models = o.list_offline_models(prefix='prefix')

也可以通过模型名获取模型并读取模型 PMML（如果支持）：

.. code:: python

    >>> model = o.get_offline_model('logistic_regression_model_name')
    >>> pmml = model.get_model()

复制离线模型可以使用下列语句：

.. code:: python

    >>> model = o.get_offline_model('logistic_regression_model_name')
    >>> # 复制到当前 project
    >>> new_model = model.copy('logistic_regression_model_name_new')
    >>> # 复制到其他 project
    >>> new_model2 = model.copy('logistic_regression_model_name_new2', project='new_project')

删除模型可使用下列语句：

.. code:: python

    >>> o.delete_offline_model('logistic_regression_model_name')
