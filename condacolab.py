"""
condacolab
Install Conda and friends on Google Colab, easily
Usage:
>>> import condacolab
>>> condacolab.install()
For more details, check the docstrings for ``install_from_url()``.
"""

import json
import os
import sys
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from subprocess import check_output, run, PIPE, STDOUT
from textwrap import dedent
from typing import Dict, AnyStr, Iterable
from urllib.error import HTTPError
import yaml
from urllib.request import urlopen
from distutils.spawn import find_executable
from IPython.display import display

from IPython import get_ipython

try:
    import ipywidgets as widgets
    HAS_IPYWIDGETS = True
except ImportError:
    HAS_IPYWIDGETS = False

try:
    import google.colab
except ImportError:
    raise RuntimeError("This module must ONLY run as part of a Colab notebook!")


__version__ = "0.1.4"
__author__ = "Jaime Rodríguez-Guerra <jaimergp@users.noreply.github.com>"


PREFIX = "/opt/conda"


# helper class for adding indentation while creating enviornment.yaml files.
class MyDumper(yaml.Dumper):

    def increase_indent(self, flow=False, indentless=False):
        return super(MyDumper, self).increase_indent(flow, False)

if HAS_IPYWIDGETS:
    restart_kernel_button = widgets.Button(description="Restart kernel now...")
    restart_button_output = widgets.Output(layout={'border': '1px solid black'})
else:
    restart_kernel_button = restart_button_output = None

def _on_button_clicked(b):
  with restart_button_output:
    get_ipython().kernel.do_shutdown(True)
    print("Kernel restarted!")
    restart_kernel_button.close()

def _run_subprocess(command, logs_filename):
    """
    Run subprocess then write the logs for that process and raise errors if it fails.
    Parameters
    ----------
    command
        Command to run while installing the packages.
    logs_filename
        Name of the file to be used for writing the logs after running the task.
    """
    print(command)
    task = run(
            command,
            check=False,
            stdout=PIPE,
            stderr=STDOUT,
            text=True,
        )

    with open(f"/content/{logs_filename}", "w") as f:
        f.write(task.stdout)
    assert (task.returncode == 0), f"💥💔💥 The installation failed! Logs are available at `/content/{logs_filename}`."


def install_from_url(
    installer_url: AnyStr,
    prefix:os.PathLike = PREFIX,
    env: Dict[AnyStr, AnyStr] = None,
    run_checks: bool = True,
    restart_kernel: bool = True,
    python_version: str = None, # conda install python{python_version}
    specs: Iterable[str] = None,  # conda install *specs
    channels: Iterable[str] = None, # conda install set these channels. 
    environment_file_url: str = None, # conda env update -f <path>
    extra_conda_args: Iterable[str] = None, 
    pip_args: Iterable[str] = None, # -r requirements, matplotlib ...

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

    condacolab_task = _run_subprocess(
        ["bash", installer_fn, "-bfp", str(prefix)],
        "condacolab_install.log",
        )
    

# Installing the following packages because Colab server expects these packages to be installed in order to launch a Python kernel:
#     - matplotlib-base
#     - psutil
#     - google-colab
#     - colabtools

    conda_exe = "mamba" if os.path.isfile(f"{prefix}/bin/mamba") else "conda"

    # check if any of those packages are already installed. If it is installed, remove it from the list of required packages.

    output = check_output([f"{prefix}/bin/conda", "list", "--json"])
    payload = json.loads(output)
    installed_names = [pkg["name"] for pkg in payload] 
    required_packages = ["matplotlib-base", "psutil", "google-colab"]
    for pkg in required_packages.copy():
        if pkg in installed_names:
            required_packages.remove(pkg)

    if required_packages:
        print("📦 Installing required packages.")
        _run_subprocess(
            [f"{prefix}/bin/{conda_exe}", "install", "-yq", *required_packages],
            "conda_task.log",
        )
        print("📦 Installation done.")

    pip_task = _run_subprocess(
        [f"{prefix}/bin/python", "-m", "pip", "-q", "install", "-U", "https://github.com/googlecolab/colabtools/archive/refs/heads/main.zip", "https://github.com/ssurbhi560/condacolab/archive/second-working-branch.tar.gz"],
        "pip_task.log"
        )

    #if environment.yaml file is provided - use that to update the conda base environment.
    if environment_file_url:
        print("📦 Updating environment using environment.yaml file...")
        _run_subprocess(
            [f"{prefix}/bin/python", "-m", "conda", "env", "update", "-n", "base", "-f", environment_file_url],
            "environment_file_update.log",
        )

        print("Environment update done.")
    
    # if any of specs, python_version, channels, pip_args, or extra_conda_args are given,
    # and evniornment.yaml file is also given then, create new enviornment.yaml file with all these specifications in it.
    # Use that enviornment.yaml file to update conda base env.
    elif environment_file_url and (specs or channels or python_version or pip_args or extra_conda_args):

        # Load the data from the file using the URL and create a file locally.
        # Change the yaml file to a python dictionary.
        # In that dictionary - add the packages specified by the user during installation something like this: 
            # if python_version: 
                #env_details["dependencies"] += [f"python={python_version}"]
                # and so on.
        # save the file.
        print("Saving the environment.yaml file locally.")
        try:
            with urlopen(environment_file_url) as response, open("/content/environment.yaml", "wb") as out:
                shutil.copyfileobj(response, out)
        except HTTPError:
            raise HTTPError("The URL you entered is not working, please check it again.")
        print("Saved locally!")

        print("Updating the environment.yaml file with new requirements you provided.")
    # if any of specs, python_version, channels, pip_args, or extra_conda_args are given,
    # and evniornment.yaml file is not given then, create new enviornment.yaml file with all these specifications in it.
    # Use that enviornment.yaml file to update conda base env.

    else:
        
        env_details = {}

        if channels: 
            env_details["channels"] = channels

        if specs:
            env_details["dependencies"] = specs

        if python_version:
            env_details["dependencies"] += [f"python={python_version}"]

        if pip_args:
            pip_args_dict = {"pip": pip_args}
            env_details["dependencies"].append(pip_args_dict) 

        # env_details["prefix"] = {prefix}

        environment_file_path = "/content/environment.yaml"
        with open(environment_file_path, 'w') as f:
            yaml.dump(env_details, f, Dumper=MyDumper, sort_keys=False, default_flow_style=False)
        _run_subprocess(
            [f"{prefix}/bin/{conda_exe}", "env", "update", "-n", "base" "-f", environment_file_path],
            "environment_file_update.log",
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
                
                mv /usr/bin/lsb_release /usr/bin/lsb_release.renamed_by_condacolab.bak
                exec {bin_path}/python $@
                """
            ).lstrip()
        )
    run(["chmod", "+x", sys.executable])


    taken = timedelta(seconds=round((datetime.now() - t0).total_seconds(), 0))
    print(f"⏲ Done in {taken}")

    if restart_kernel:
        print("🔁 Restarting kernel...")
        get_ipython().kernel.do_shutdown(True)

    elif HAS_IPYWIDGETS:
        print("🔁 Please restart kernel...")
        restart_kernel_button.on_click(_on_button_clicked)
        display(restart_kernel_button, restart_button_output)

    else:
        print("🔁 Please restart kernel by clicking on Runtime > Restart runtime.")

def install_mambaforge(
    prefix: os.PathLike = PREFIX, 
    env: Dict[AnyStr, AnyStr] = None, 
    run_checks: bool = True, 
    restart_kernel: bool = True,
    specs: Iterable[str] = None,
    python_version: str = None,
    channels: Iterable[str] = None, # conda install set these channels.
    environment_file_url: str = None, # conda env update -f <path>
    extra_conda_args: Iterable[str] = None, 
    pip_args: Iterable[str] = None, # -r requirements, matplotlib ...

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
    install_from_url(
        installer_url, 
        prefix=prefix, 
        env=env, 
        run_checks=run_checks, 
        restart_kernel=restart_kernel, 
        specs=specs, 
        python_version=python_version,
        channels=channels,
        environment_file_url=environment_file_url,
        extra_conda_args=extra_conda_args,
        pip_args=pip_args,
        )


# Make mambaforge the default
install = install_mambaforge


def install_miniforge(
    prefix: os.PathLike = PREFIX, env: Dict[AnyStr, AnyStr] = None, run_checks: bool = True, restart_kernel: bool = True,
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
    install_from_url(installer_url, prefix=prefix, env=env, run_checks=run_checks, restart_kernel=restart_kernel)


def install_miniconda(
    prefix: os.PathLike = PREFIX, env: Dict[AnyStr, AnyStr] = None, run_checks: bool = True, restart_kernel: bool = True,
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
    install_from_url(installer_url, prefix=prefix, env=env, run_checks=run_checks, restart_kernel=restart_kernel)


def install_anaconda(
    prefix: os.PathLike = PREFIX, env: Dict[AnyStr, AnyStr] = None, run_checks: bool = True, restart_kernel: bool = True,
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
    install_from_url(installer_url, prefix=prefix, env=env, run_checks=run_checks, restart_kernel=restart_kernel)


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
    assert sitepackages in sys.path, f"💥💔💥 PYTHONPATH was not patched! Value: {sys.path}"
    assert all(
        not path.startswith("/usr/local/") for path in sys.path
    ), f"💥💔💥 PYTHONPATH include system locations: {[path for path in sys.path if path.startswith('/usr/local')]}!"
    assert (
        f"{prefix}/bin" in os.environ["PATH"]
    ), f"💥💔💥 PATH was not patched! Value: {os.environ['PATH']}"
    assert (
        prefix == os.environ.get("CONDA_PREFIX")
    ), f"💥💔💥 CONDA_PREFIX value: {os.environ.get('CONDA_PREFIX', '<not set>')} does not match conda installation location {prefix}!"

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