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

import datetime
import os
import shutil
import tempfile
import time
import uuid

import mock
import pytest

from .. import ODPS, errors, options
from ..accounts import (
    BearerTokenAccount,
    CredentialProviderAccount,
    SignServer,
    SignServerAccount,
    SignServerError,
)
from ..rest import RestClient
from .core import tn

try:
    from cupid.runtime import context as cupid_context
except ImportError:
    cupid_context = None


@pytest.fixture(autouse=True)
def clear_global_accounts():
    try:
        yield
    finally:
        options.account = options.default_project = options.endpoint = None


def test_sign_server_account(odps):
    server = SignServer()
    server.accounts[odps.account.access_id] = odps.account.secret_access_key
    try:
        server.start(('127.0.0.1', 0))
        account = SignServerAccount(odps.account.access_id, server.server.server_address)
        odps = odps.as_account(account=account)
        odps.delete_table(tn('test_sign_account_table'), if_exists=True)
        t = odps.create_table(tn('test_sign_account_table'), 'col string', lifecycle=1)
        assert odps.exist_table(tn('test_sign_account_table')) is True
        t.drop(async_=True)
    finally:
        server.stop()


def test_tokenized_sign_server_account(odps):
    server = SignServer(token=str(uuid.uuid4()))
    server.accounts[odps.account.access_id] = odps.account.secret_access_key
    try:
        server.start(('127.0.0.1', 0))
        account = SignServerAccount(odps.account.access_id, server.server.server_address)
        odps = ODPS(None, None, odps.project, odps.endpoint, account=account)
        pytest.raises(SignServerError, lambda: odps.delete_table(tn('test_sign_account_table'), if_exists=True))

        account = SignServerAccount(odps.account.access_id, server.server.server_address, token=server.token)
        odps = ODPS(None, None, odps.project, odps.endpoint, account=account)
        odps.delete_table(tn('test_sign_account_table'), if_exists=True)
        t = odps.create_table(tn('test_sign_account_table'), 'col string', lifecycle=1)
        assert odps.exist_table(tn('test_sign_account_table')) is True
        t.drop(async_=True)
    finally:
        server.stop()


@pytest.mark.skipif(cupid_context is None, reason="cannot import cupid context")
def test_bearer_token_account(odps):
    odps.delete_table(tn('test_bearer_token_account_table'), if_exists=True)
    t = odps.create_table(tn('test_bearer_token_account_table'), 'col string', lifecycle=1)
    with t.open_writer() as writer:
        records = [['val1'], ['val2'], ['val3']]
        writer.write(records)

    inst = odps.execute_sql(
        'select count(*) from {0}'.format(tn('test_bearer_token_account_table')), async_=True
    )
    inst.wait_for_success()
    task_name = inst.get_task_names()[0]

    logview_address = inst.get_logview_address()
    token = logview_address[logview_address.find('token=') + len('token='):]
    bearer_token_account = BearerTokenAccount(token=token)
    bearer_token_odps = ODPS(
        None, None, odps.project, odps.endpoint, account=bearer_token_account
    )
    bearer_token_instance = bearer_token_odps.get_instance(inst.id)

    assert inst.get_task_result(task_name) == bearer_token_instance.get_task_result(task_name)
    assert inst.get_task_summary(task_name) == bearer_token_instance.get_task_summary(task_name)

    with pytest.raises(errors.NoPermission):
        bearer_token_odps.create_table(tn('test_bearer_token_account_table_test1'),
                                       'col string', lifecycle=1)

    fake_token_account = BearerTokenAccount(token='fake-token')
    bearer_token_odps = ODPS(
        None, None, odps.project, odps.endpoint, account=fake_token_account
    )

    with pytest.raises(errors.ODPSError):
        bearer_token_odps.create_table(tn('test_bearer_token_account_table_test2'),
                                       'col string', lifecycle=1)

    tmp_path = tempfile.mkdtemp(prefix="tmp_pyodps_")
    try:
        token_file_name = os.path.join(tmp_path, "token_file")
        with open(token_file_name, "w") as token_file:
            token_file.write(token)
        os.environ["ODPS_BEARER_TOKEN_FILE"] = token_file_name

        token_ts_file_name = os.path.join(tmp_path, "token_ts_file")
        create_timestamp = int(time.time())
        with open(token_ts_file_name, "w") as token_ts_file:
            token_ts_file.write(str(create_timestamp))
        os.environ["ODPS_BEARER_TOKEN_TIMESTAMP_FILE"] = token_ts_file_name

        env_odps = ODPS(project=odps.project, endpoint=odps.endpoint)
        assert isinstance(env_odps.account, BearerTokenAccount)
        assert env_odps.account.token == token
        assert env_odps.account._last_modified_time == datetime.datetime.fromtimestamp(create_timestamp)
    finally:
        shutil.rmtree(tmp_path)
        os.environ.pop("ODPS_BEARER_TOKEN_FILE")
        os.environ.pop("ODPS_BEARER_TOKEN_TIMESTAMP_FILE")


def test_v4_signature_fallback(odps_daily):
    odps = odps_daily
    odps.delete_table(tn('test_sign_account_table'), if_exists=True)
    assert odps.endpoint not in RestClient._endpoints_without_v4_sign

    def _new_is_ok(self, resp):
        if odps.endpoint not in self._endpoints_without_v4_sign:
            raise errors.InvalidParameter("ODPS-0410051: Invalid credentials")
        return resp.ok

    def _new_is_ok2(self, resp):
        if odps.endpoint not in self._endpoints_without_v4_sign:
            raise errors.InternalServerError(
                "ODPS-0010000:System internal error - Error occurred while getting access key for "
                "'%s', AliyunV4 request need ak v3 support" % odps_daily.account.access_id
            )
        return resp.ok

    def _new_is_ok3(self, resp):
        if odps.endpoint not in self._endpoints_without_v4_sign:
            raise errors.Unauthorized("The request authorization header is invalid or missing.")
        return resp.ok

    old_enable_v4_sign = options.enable_v4_sign
    try:
        options.enable_v4_sign = True
        RestClient._endpoints_without_v4_sign.clear()
        with mock.patch("odps.rest.RestClient.is_ok", new=_new_is_ok):
            odps.delete_table(tn('test_sign_account_table'), if_exists=True)
            assert odps.endpoint in RestClient._endpoints_without_v4_sign

        RestClient._endpoints_without_v4_sign.clear()
        with mock.patch("odps.rest.RestClient.is_ok", new=_new_is_ok2):
            odps.delete_table(tn('test_sign_account_table'), if_exists=True)
            assert odps.endpoint in RestClient._endpoints_without_v4_sign

        RestClient._endpoints_without_v4_sign.clear()
        with mock.patch("odps.rest.RestClient.is_ok", new=_new_is_ok3):
            odps.delete_table(tn('test_sign_account_table'), if_exists=True)
            assert odps.endpoint in RestClient._endpoints_without_v4_sign
    finally:
        RestClient._endpoints_without_v4_sign.difference_update([odps.endpoint])
        options.enable_v4_sign = old_enable_v4_sign


def test_credential_provider_account(odps):
    class MockCredentials(object):
        @classmethod
        def get_access_key_id(cls):
            return odps.account.access_id

        @classmethod
        def get_access_key_secret(cls):
            return odps.account.secret_access_key

        @classmethod
        def get_security_token(cls):
            return None  # kept empty to skip sts token check

    class MockCredentialProvider(object):
        @classmethod
        def get_credentials(cls):
            return MockCredentials()

    account = CredentialProviderAccount(MockCredentialProvider())
    cred_odps = ODPS(
        account, None, odps.project, odps.endpoint
    )

    table_name = tn('test_bearer_token_account_table')

    cred_odps.delete_table(table_name, if_exists=True)
    t = cred_odps.create_table(table_name, 'col string', lifecycle=1)
    with t.open_writer() as writer:
        records = [['val1'], ['val2'], ['val3']]
        writer.write(records)
    cred_odps.delete_table(table_name)
