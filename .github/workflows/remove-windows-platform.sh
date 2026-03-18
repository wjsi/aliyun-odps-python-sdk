#!/bin/bash
# Remove Windows platform restriction from Cython requirements in pyproject.toml
# This allows building wheels for Python 3.13+ on all platforms

sed -i.bak "s/platform_system!='Windows' and //g" pyproject.toml
sed -i.bak "s/platform_system!='Windows'//g" pyproject.toml
rm -f pyproject.toml.bak
