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

from copy import deepcopy

import pytest

from ..accounts import CloudAccount
from ..config import (
    Config,
    OptionError,
    any_validator,
    is_integer,
    is_null,
    option_context,
    options,
)


def test_options():
    old_config = Config(deepcopy(options._config))

    with option_context() as local_options:
        if options.account is None:
            assert options.account == old_config.account
        else:
            assert options.account.access_id == old_config.account.access_id
            assert (
                options.account.secret_access_key
                == old_config.account.secret_access_key
            )
        assert options.endpoint == old_config.endpoint
        assert options.default_project == old_config.default_project
        assert local_options.tunnel.endpoint is None
        assert local_options.chunk_size > 0
        assert local_options.connect_timeout > 0
        assert local_options.read_timeout > 0
        assert local_options.console.max_lines is None
        assert local_options.console.max_width is None

        local_options.account = CloudAccount("test", "")
        assert local_options.account.access_id == "test"

        local_options.register_option(
            "nest.inner.value", 50, validator=any_validator(is_null, is_integer)
        )
        assert local_options.nest.inner.value == 50

        def set(val):
            local_options.nest.inner.value = val

        pytest.raises(ValueError, lambda: set("test"))
        set(None)
        assert local_options.nest.inner.value is None
        set(30)
        assert local_options.nest.inner.value == 30

        local_options.console.max_width = 40
        assert local_options.console.max_width == 40
        local_options.console.max_lines = 30
        assert local_options.console.max_lines == 30

    if options.account is None:
        assert options.account == old_config.account
    else:
        assert options.account.access_id == old_config.account.access_id
        assert options.account.secret_access_key == old_config.account.secret_access_key
    assert options.endpoint == old_config.endpoint
    assert options.default_project == old_config.default_project
    assert options.tunnel.endpoint is None
    assert options.chunk_size > 0
    assert options.connect_timeout > 0
    assert options.read_timeout > 0
    assert options.console.max_lines is None
    assert options.console.max_width is None
    pytest.raises(AttributeError, lambda: options.nest.inner.value)

    def set_notexist():
        options.display.val = 3

    pytest.raises(OptionError, set_notexist)


def test_redirection():
    local_config = Config()

    local_config.register_option("test.redirect_src", 10)
    local_config.redirect_option("test.redirect_redir", "test.redirect_src")

    assert "test" in dir(local_config)
    assert "redirect_redir" in dir(local_config.test)

    local_config.test.redirect_redir = 20
    assert local_config.test.redirect_src == 20
    local_config.test.redirect_src = 10
    assert local_config.test.redirect_redir == 10

    local_config.unregister_option("test.redirect_redir")
    local_config.unregister_option("test.redirect_src")
    pytest.raises(AttributeError, lambda: local_config.test.redirect_redir)
    pytest.raises(AttributeError, lambda: local_config.test.redirect_src)


def test_set_display_option():
    options.display.max_rows = 10
    options.display.unicode.ambiguous_as_wide = True
    assert options.display.max_rows == 10
    assert options.display.unicode.ambiguous_as_wide is True
    options.register_pandas("display.non_exist", True)
    assert options.display.non_exist

    try:
        import pandas as pd

        assert pd.options.display.max_rows == 10
        assert pd.options.display.unicode.ambiguous_as_wide is True
    except ImportError:
        pass


def test_dump_and_load():
    with option_context() as local_options:
        local_options.register_option(
            "test.value", 50, validator=any_validator(is_null, is_integer)
        )
        d = local_options.dumps()
        assert d["test.value"] == 50

        d["test.value"] = 100
        local_options.loads(d)
        assert local_options.test.value == 100


def test_add_validator():
    with option_context() as local_options:
        local_options.register_option(
            "test.value", 50, validator=any_validator(is_null, is_integer)
        )
        with pytest.raises(ValueError):
            local_options.test.value = "abcd"

        values = []

        def _validator(val):
            values.append(val)
            return True

        local_options.add_validator("test.value", _validator)
        local_options.test.value = 1234
        assert values == [1234]
