"""
condacolab
Install Conda and friends on Google Colab, easily

Usage:

>>> import condacolab
>>> condacolab.install()

For more details, check the docstrings for ``install_from_url()``.
"""

import os
import sys
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from subprocess import run, PIPE, STDOUT
from textwrap import dedent
from typing import Dict, AnyStr
from urllib.request import urlopen
from distutils.spawn import find_executable
import ipywidgets as widgets
from IPython.display import display

from IPython import get_ipython

try:
    import google.colab
except ImportError:
    raise RuntimeError("This module must ONLY run as part of a Colab notebook!")


__version__ = "0.1.4"
__author__ = "Jaime Rodríguez-Guerra <jaimergp@users.noreply.github.com>"


PREFIX = "/opt/miniconda"

def run_subprocess(bash_command, logs_filename):
    """
    Run subprocess then write the logs for that process and raise errors if it fails.

        Parameters
        ----------
        bash_command
            Bash command to run while installing the packages.

        logs_filename
            Name of the file to be used for writing the logs after running the task.

    """
    task = run(
            bash_command,
            check=False,
            stdout=PIPE,
            stderr=STDOUT,
            text=True,
        )

    with open(logs_filename, "w") as f:
        f.write(task.stdout)
    assert ( task.returncode == 0
    ), f"💥💔💥 The installation failed! Logs are available at `/content/{logs_filename}`."


button = widgets.Button(description="Restart kernel now...")
output = widgets.Output(layout={'border': '1px solid black'})

def on_button_clicked(b):
  # Display the message within the output widget.
  with output:
    get_ipython().kernel.do_shutdown(True)
    print("Kernel restarted...")
    button.close()

def install_from_url(
    installer_url: AnyStr,
    prefix: os.PathLike = PREFIX,
    env: Dict[AnyStr, AnyStr] = None,
    run_checks: bool = True,
):
    """
    Download and run a constructor-like installer, patching
    the necessary bits so it works on Colab right away.

    This will restart your kernel as a result!

    Parameters
    ----------
    installer_url
        URL pointing to a ``constructor``-like installer, such
        as Miniconda or Mambaforge
    prefix
        Target location for the installation
    env
        Environment variables to inject in the kernel restart.
        We *need* to inject ``LD_LIBRARY_PATH`` so ``{PREFIX}/lib``
        is first, but you can also add more if you need it. Take
        into account that no quote handling is done, so you need
        to add those yourself in the raw string. They will
        end up added to a line like ``exec env VAR=VALUE python3...``.
        For example, a value with spaces should be passed as::

            env={"VAR": '"a value with spaces"'}
    run_checks
        Run checks to see if installation was run previously.
        Change to False to ignore checks and always attempt
        to run the installation.
    """
    if run_checks:
        try:  # run checks to see if it this was run already
            return check(prefix)
        except AssertionError:
            pass  # just install

    t0 = datetime.now()
    print(f"⏬ Downloading {installer_url}...")
    installer_fn = "__installer__.sh"
    with urlopen(installer_url) as response, open(installer_fn, "wb") as out:
        shutil.copyfileobj(response, out)

    print("📦 Installing...")

    condacolab_task = run_subprocess(
        ["bash", installer_fn, "-bfp", str(prefix)], 
        "condacolab_install.log",
        )

    """ 
    Installing the following packages because Colab server expects these packages to be installed in order to launch a Python kernel :
        - matplotlib-base
        - psutil
        - google-colab
        - colabtools
    """

    conda_exe = "mamba" if os.path.isfile(f"{prefix}/bin/mamba") else "conda"

    conda_task = run_subprocess(
        [f"{prefix}/bin/{conda_exe}", "install", "-yq", "matplotlib-base", "psutil", "google-colab"], 
        "conda_task.log",
        )

    pip_task = run_subprocess(
        [f"{prefix}/bin/python", "-m", "pip", "-q", "install", "-U", "https://github.com/googlecolab/colabtools/archive/refs/heads/main.zip", 
        "condacolab"], "pip_task.log",
        )

    print("📌 Adjusting configuration...")
    cuda_version = ".".join(os.environ.get("CUDA_VERSION", "*.*.*").split(".")[:2])
    prefix = Path(prefix)
    condameta = prefix / "conda-meta"
    condameta.mkdir(parents=True, exist_ok=True)
    pymaj, pymin = sys.version_info[:2]

    with open(condameta / "pinned", "a") as f:
        f.write(f"python {pymaj}.{pymin}.*\n")
        f.write(f"python_abi {pymaj}.{pymin}.* *cp{pymaj}{pymin}*\n")
        f.write(f"cudatoolkit {cuda_version}.*\n")

    with open(prefix / ".condarc", "a") as f:
        f.write("always_yes: true\n")

    with open("/etc/ipython/ipython_config.py", "a") as f:
        f.write(
            f"""\nc.InteractiveShellApp.exec_lines = [
                    "import sys",
                    "sp = f'{prefix}/lib/python{pymaj}.{pymin}/site-packages'",
                    "if sp not in sys.path:",
                    "    sys.path.insert(0, sp)",
                ]
            """
        )
    sitepackages = f"{prefix}/lib/python{pymaj}.{pymin}/site-packages"
    if sitepackages not in sys.path:
        sys.path.insert(0, sitepackages)

    env = env or {}
    bin_path = f"{prefix}/bin"

    os.rename(sys.executable, f"{sys.executable}.renamed_by_condacolab.bak")
    with open(sys.executable, "w") as f:
        f.write(
            dedent(
                f"""
                #!/bin/bash
                source {prefix}/etc/profile.d/conda.sh
                conda activate
                unset PYTHONPATH
                rm -rf /usr/bin/lsb_release
                exec {bin_path}/python $@
                """
            ).lstrip()
        )
    run(["chmod", "+x", sys.executable])
    # run(["sudo", "rm", "/usr/bin/lsb_release"]) # see this to know why we are doing this : https://github.com/pypa/pip/issues/4924

    taken = timedelta(seconds=round((datetime.now() - t0).total_seconds(), 0))
    print(f"⏲ Done in {taken}")

    print("🔁 Please restart the kernel...")
    # get_ipython().kernel.do_shutdown(True)
    button.on_click(on_button_clicked)
    display(button, output)

def install_mambaforge(
    prefix: os.PathLike = PREFIX, env: Dict[AnyStr, AnyStr] = None, run_checks: bool = True
):
    """
    Install Mambaforge, built for Python 3.7.

    Mambaforge consists of a Miniconda-like distribution optimized
    and preconfigured for conda-forge packages, and includes ``mamba``,
    a faster ``conda`` implementation.

    Unlike the official Miniconda, this is built with the latest ``conda``.

    Parameters
    ----------
    prefix
        Target location for the installation
    env
        Environment variables to inject in the kernel restart.
        We *need* to inject ``LD_LIBRARY_PATH`` so ``{PREFIX}/lib``
        is first, but you can also add more if you need it. Take
        into account that no quote handling is done, so you need
        to add those yourself in the raw string. They will
        end up added to a line like ``exec env VAR=VALUE python3...``.
        For example, a value with spaces should be passed as::

            env={"VAR": '"a value with spaces"'}
    run_checks
        Run checks to see if installation was run previously.
        Change to False to ignore checks and always attempt
        to run the installation.
    """
    installer_url = r"https://github.com/jaimergp/miniforge/releases/latest/download/Mambaforge-colab-Linux-x86_64.sh"
    install_from_url(installer_url, prefix=prefix, env=env, run_checks=run_checks)


# Make mambaforge the default
install = install_mambaforge


def install_miniforge(
    prefix: os.PathLike = PREFIX, env: Dict[AnyStr, AnyStr] = None, run_checks: bool = True
):
    """
    Install Mambaforge, built for Python 3.7.

    Mambaforge consists of a Miniconda-like distribution optimized
    and preconfigured for conda-forge packages.

    Unlike the official Miniconda, this is built with the latest ``conda``.

    Parameters
    ----------
    prefix
        Target location for the installation
    env
        Environment variables to inject in the kernel restart.
        We *need* to inject ``LD_LIBRARY_PATH`` so ``{PREFIX}/lib``
        is first, but you can also add more if you need it. Take
        into account that no quote handling is done, so you need
        to add those yourself in the raw string. They will
        end up added to a line like ``exec env VAR=VALUE python3...``.
        For example, a value with spaces should be passed as::

            env={"VAR": '"a value with spaces"'}
    run_checks
        Run checks to see if installation was run previously.
        Change to False to ignore checks and always attempt
        to run the installation.
    """
    installer_url = r"https://github.com/jaimergp/miniforge/releases/latest/download/Miniforge-colab-Linux-x86_64.sh"
    install_from_url(installer_url, prefix=prefix, env=env, run_checks=run_checks)


def install_miniconda(
    prefix: os.PathLike = PREFIX, env: Dict[AnyStr, AnyStr] = None, run_checks: bool = True
):
    """
    Install Miniconda 4.12.0 for Python 3.7.

    Parameters
    ----------
    prefix
        Target location for the installation
    env
        Environment variables to inject in the kernel restart.
        We *need* to inject ``LD_LIBRARY_PATH`` so ``{PREFIX}/lib``
        is first, but you can also add more if you need it. Take
        into account that no quote handling is done, so you need
        to add those yourself in the raw string. They will
        end up added to a line like ``exec env VAR=VALUE python3...``.
        For example, a value with spaces should be passed as::

            env={"VAR": '"a value with spaces"'}
    run_checks
        Run checks to see if installation was run previously.
        Change to False to ignore checks and always attempt
        to run the installation.
    """
    installer_url = r"https://repo.anaconda.com/miniconda/Miniconda3-py37_4.12.0-Linux-x86_64.sh"
    install_from_url(installer_url, prefix=prefix, env=env, run_checks=run_checks)


def install_anaconda(
    prefix: os.PathLike = PREFIX, env: Dict[AnyStr, AnyStr] = None, run_checks: bool = True
):
    """
    Install Anaconda 2022.05, the latest version built
    for Python 3.7 at the time of update.

    Parameters
    ----------
    prefix
        Target location for the installation
    env
        Environment variables to inject in the kernel restart.
        We *need* to inject ``LD_LIBRARY_PATH`` so ``{PREFIX}/lib``
        is first, but you can also add more if you need it. Take
        into account that no quote handling is done, so you need
        to add those yourself in the raw string. They will
        end up added to a line like ``exec env VAR=VALUE python3...``.
        For example, a value with spaces should be passed as::

            env={"VAR": '"a value with spaces"'}
    run_checks
        Run checks to see if installation was run previously.
        Change to False to ignore checks and always attempt
        to run the installation.
    """
    installer_url = r"https://repo.anaconda.com/archive/Anaconda3-2022.05-Linux-x86_64.sh"
    install_from_url(installer_url, prefix=prefix, env=env, run_checks=run_checks)


def check(prefix: os.PathLike = PREFIX, verbose: bool = True):
    """
    Run some basic checks to ensure that ``conda`` has been installed
    correctly

    Parameters
    ----------
    prefix
        Location where ``conda`` was installed (should match the one
        provided for ``install()``.
    verbose
        Print success message if True
    """
    assert find_executable("conda"), "💥💔💥 Conda not found!"

    pymaj, pymin = sys.version_info[:2]
    sitepackages = f"{prefix}/lib/python{pymaj}.{pymin}/site-packages"
    print(sitepackages)
    assert sitepackages in sys.path, f"💥💔💥 PYTHONPATH was not patched! Value: {sys.path}"
    assert (
        f"{prefix}/bin" in os.environ["PATH"]
    ), f"💥💔💥 PATH was not patched! Value: {os.environ['PATH']}"
    # assert (
    #     f"{prefix}/lib" in os.environ["LD_LIBRARY_PATH"]
    # ), f"💥💔💥 LD_LIBRARY_PATH was not patched! Value: {os.environ['LD_LIBRARY_PATH']}"
    if verbose:
        print("✨🍰✨ Everything looks OK!")


__all__ = [
    "install",
    "install_from_url",
    "install_mambaforge",
    "install_miniforge",
    "install_miniconda",
    "install_anaconda",
    "check",
    "PREFIX",
]
