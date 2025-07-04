#!/usr/bin/env python
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

# Parts of this file were taken from the pandas project
# (https://github.com/pandas-dev/pandas), which is permitted for use under
# the BSD 3-Clause License

import os
import platform
import shutil
import sys

from setuptools import Extension, find_packages, setup
from setuptools.command.install import install

try:
    from setuptools import Command
except ImportError:
    from distutils.cmd import Command
try:
    from sysconfig import get_config_var
except ImportError:
    from distutils.sysconfig import get_config_var
try:
    from packaging.version import Version
except ImportError:
    from distutils.version import LooseVersion as Version

# From https://github.com/pandas-dev/pandas/pull/24274:
# For mac, ensure extensions are built for macos 10.9 when compiling on a
# 10.9 system or above, overriding distuitls behaviour which is to target
# the version that python was built for. This may be overridden by setting
# MACOSX_DEPLOYMENT_TARGET before calling setup.py
if sys.platform == "darwin":
    if "MACOSX_DEPLOYMENT_TARGET" not in os.environ:
        current_system = Version(platform.mac_ver()[0])
        python_target = Version(get_config_var("MACOSX_DEPLOYMENT_TARGET"))
        if python_target < Version("10.9") and current_system >= Version("10.9"):
            os.environ["MACOSX_DEPLOYMENT_TARGET"] = "10.9"

repo_root = os.path.dirname(os.path.abspath(__file__))

try:
    execfile
except NameError:

    def execfile(fname, globs, locs=None):
        locs = locs or globs
        exec(compile(open(fname).read(), fname, "exec"), globs, locs)


version_ns = {}
execfile(os.path.join(repo_root, "odps", "_version.py"), version_ns)

extra_install_cmds = []


def which(program):
    import os

    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None


# http://stackoverflow.com/questions/12683834/how-to-copy-directory-recursively-in-python-and-overwrite-all
def recursive_overwrite(src, dest, filter_func=None):
    destinations = []
    filter_func = filter_func or (lambda s: True)
    if os.path.isdir(src):
        if not os.path.isdir(dest):
            os.makedirs(dest)
        files = os.listdir(src)
        for f in files:
            if not filter_func(f):
                continue
            destinations.extend(
                recursive_overwrite(os.path.join(src, f), os.path.join(dest, f))
            )
    else:
        shutil.copyfile(src, dest)
        destinations.append(dest)
    return destinations


class CustomInstall(install):
    def run(self):
        global extra_install_cmds
        install.run(self)
        [self.run_command(cmd) for cmd in extra_install_cmds]


version = sys.version_info
PY2 = version[0] == 2
PY3 = version[0] == 3
PYPY = platform.python_implementation().lower() == "pypy"

if PY2 and version[:2] < (2, 7):
    raise Exception("PyODPS supports Python 2.7+ (including Python 3+).")

try:
    import distribute

    raise Exception(
        "PyODPS cannot be installed when 'distribute' is installed. "
        "Please uninstall it before installing PyODPS."
    )
except ImportError:
    pass

try:
    import pip

    for pk in pip.get_installed_distributions():
        if pk.key == "odps":
            raise Exception(
                "Package `odps` collides with PyODPS. Please uninstall it before installing PyODPS."
            )
except (ImportError, AttributeError):
    pass

try:
    from jupyter_core.paths import jupyter_data_dir

    has_jupyter = True
except ImportError:
    has_jupyter = False

if len(sys.argv) > 1 and sys.argv[1] == "clean":
    build_cmd = sys.argv[1]
else:
    build_cmd = None

requirements = []
with open("requirements.txt") as f:
    requirements.extend(f.read().splitlines())

full_requirements = [
    "jupyter>=1.0.0",
    "ipython>=4.0.0",
    "numpy>=1.6.0",
    "pandas>=0.17.0",
    "matplotlib>=1.4",
    "graphviz>=0.4",
    "greenlet>=0.4.10",
    "ipython<6.0.0; python_version < \"3\"",
    "cython>=0.20; sys_platform != \"win32\"",
]
mars_requirements = [
    "pymars>=0.5.4",
    "protobuf>=3.6,<4.0",
]

long_description = None
if os.path.exists("README.rst"):
    with open("README.rst") as f:
        long_description = f.read()

setup_options = dict(
    name="pyodps",
    version=version_ns["__version__"],
    description="ODPS Python SDK and data analysis framework",
    long_description=long_description,
    author="Wu Wei",
    author_email="weiwu@cacheme.net",
    maintainer="Wenjun Si",
    maintainer_email="wenjun.swj@alibaba-inc.com",
    url="http://github.com/aliyun/aliyun-odps-python-sdk",
    license="Apache License 2.0",
    classifiers=[
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: Implementation :: CPython",
        "Programming Language :: Python :: Implementation :: PyPy",
        "Topic :: Software Development :: Libraries",
    ],
    cmdclass={"install": CustomInstall},
    packages=find_packages(exclude=("*.tests.*", "*.tests")),
    include_package_data=True,
    install_requires=requirements,
    include_dirs=[],
    extras_require={"full": full_requirements, "mars": mars_requirements},
    entry_points={
        "sqlalchemy.dialects": [
            "odps = odps.sqlalchemy_odps:ODPSDialect",
            "maxcompute = odps.sqlalchemy_odps:ODPSDialect",
        ],
        "superset.db_engine_specs": [
            "odps = odps.superset_odps:ODPSEngineSpec",
            "maxcompute = odps.superset_odps:ODPSEngineSpec",
        ],
        "console_scripts": [
            "pyou = odps_scripts.pyou:main",
            "pyodps-pack = odps_scripts.pyodps_pack:main",
        ],
    },
)

if build_cmd != "clean" and not PYPY:  # skip cython in pypy
    try:
        import cython
        from Cython.Build import cythonize
        from Cython.Distutils import build_ext

        # detect if cython works
        if sys.platform == "win32":
            cython.inline("return a + b", a=1, b=1)

        cythonize_kw = dict(language_level=sys.version_info[0])
        extension_kw = dict(language="c++", include_dirs=[])
        if "MSC" in sys.version:
            extra_compile_args = ["/Ot", "/I" + os.path.join(repo_root, "misc")]
            extension_kw["extra_compile_args"] = extra_compile_args
        else:
            extra_compile_args = ["-O3"]
            extension_kw["extra_compile_args"] = extra_compile_args

        if os.environ.get("CYTHON_TRACE"):
            extension_kw["define_macros"] = [
                ("CYTHON_TRACE_NOGIL", "1"),
                ("CYTHON_TRACE", "1"),
            ]
            cythonize_kw["compiler_directives"] = {"linetrace": True}

        extensions = [
            Extension("odps.src.types_c", ["odps/src/types_c.pyx"], **extension_kw),
            Extension("odps.src.crc32c_c", ["odps/src/crc32c_c.pyx"], **extension_kw),
            Extension("odps.src.utils_c", ["odps/src/utils_c.pyx"], **extension_kw),
            Extension(
                "odps.tunnel.pb.encoder_c",
                ["odps/tunnel/pb/encoder_c.pyx"],
                **extension_kw
            ),
            Extension(
                "odps.tunnel.pb.decoder_c",
                ["odps/tunnel/pb/decoder_c.pyx"],
                **extension_kw
            ),
            Extension(
                "odps.tunnel.io.writer_c",
                ["odps/tunnel/io/writer_c.pyx"],
                **extension_kw
            ),
            Extension(
                "odps.tunnel.io.reader_c",
                ["odps/tunnel/io/reader_c.pyx"],
                **extension_kw
            ),
            Extension(
                "odps.tunnel.checksum_c", ["odps/tunnel/checksum_c.pyx"], **extension_kw
            ),
            Extension(
                "odps.tunnel.hasher_c", ["odps/tunnel/hasher_c.pyx"], **extension_kw
            ),
        ]

        setup_options["cmdclass"].update({"build_ext": build_ext})
        force_recompile = bool(int(os.getenv("CYTHON_FORCE_RECOMPILE", "0")))
        setup_options["ext_modules"] = cythonize(
            extensions, force=force_recompile, **cythonize_kw
        )
    except:
        pass

if build_cmd != "clean" and has_jupyter:

    class InstallJS(Command):
        description = "install JavaScript extensions"
        user_options = []

        def initialize_options(self):
            pass

        def finalize_options(self):
            pass

        def run(self):
            src_dir = os.path.join(repo_root, "odps", "static", "ui", "target")
            if not os.path.exists(src_dir):
                return

            dest_dir = os.path.join(jupyter_data_dir(), "nbextensions", "pyodps")
            if os.path.exists(dest_dir):
                shutil.rmtree(dest_dir)
            if not os.path.exists(dest_dir):
                os.makedirs(dest_dir)
            recursive_overwrite(src_dir, dest_dir)

            try:
                from notebook.nbextensions import enable_nbextension
            except ImportError:
                return
            enable_nbextension("notebook", "pyodps/main")

    class BuildJS(Command):
        description = "build JavaScript files"
        user_options = [("registry=", None, "npm registry")]

        def initialize_options(self):
            self.registry = None

        def finalize_options(self):
            pass

        def run(self):
            if not which("npm"):
                raise Exception("You need to install npm before building the scripts.")

            cwd = os.getcwd()

            ui_path = os.path.join(os.path.abspath(os.getcwd()), "odps", "static", "ui")
            if not os.path.exists(ui_path):
                return

            os.chdir(ui_path)
            cmd = "npm install"
            if getattr(self, "registry", None):
                cmd += " --registry=" + self.registry
            print("executing " + cmd)
            ret = os.system(cmd)
            ret >>= 8
            if ret != 0:
                print(cmd + " exited with error: %d" % ret)

            print("executing grunt")
            ret = os.system("npm run grunt")
            ret >>= 8
            if ret != 0:
                print("grunt exited with error: %d" % ret)

            os.chdir(cwd)

    setup_options["cmdclass"].update({"install_js": InstallJS, "build_js": BuildJS})
    extra_install_cmds.append("install_js")

setup(**setup_options)

if build_cmd == "clean":
    for root, dirs, files in os.walk(os.path.normpath("odps/")):
        pyx_files = set()
        c_file_pairs = []
        if "__pycache__" in dirs:
            full_path = os.path.join(root, "__pycache__")
            print("removing '%s'" % full_path)
            shutil.rmtree(full_path)
        for f in files:
            fn, ext = os.path.splitext(f)
            # delete compiled binaries
            if ext.lower() in (".pyd", ".so", ".pyc"):
                full_path = os.path.join(root, f)
                print("removing '%s'" % full_path)
                os.unlink(full_path)
            elif ext.lower() == ".pyx":
                pyx_files.add(fn)
            elif ext.lower() in (".c", ".cpp", ".cc"):
                c_file_pairs.append((fn, f))

        # remove cython-generated files
        for cfn, cf in c_file_pairs:
            if cfn in pyx_files:
                full_path = os.path.join(root, cf)
                print("removing '%s'" % full_path)
                os.unlink(full_path)
