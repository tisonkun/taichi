import argparse
import functools
import sys
from enum import Enum
from functools import reduce
from pathlib import Path

OS = {
    "windows": (),
    "macos": (),
    "ubuntu": (
        "18.04",
        "20.04",
    )
}
HARDWARE = ("cpu", "gpu")

CPU_BASE_BLOCK = """# Taichi Dockerfile for development
FROM {os}:{version}
"""

GPU_BASE_BLOCK = """# Taichi Dockerfile for development
FROM nvidia/cudagl:11.2.2-devel-ubuntu{version}
# Use 11.2 instead of 11.4 to avoid forward compatibility issue on Nvidia driver 460
"""

CPU_APT_INSTALL_BLOCK = """
RUN apt-get update && \\
    apt-get install -y software-properties-common \\
                       python3-pip \\
                       libtinfo-dev \\
                       clang-10 \\
                       wget \\
                       git \\
                       unzip \\
                       libx11-xcb-dev
"""

GPU_APT_INSTALL_BLOCK = """
RUN apt-get update && \\
    apt-get install -y software-properties-common \\
                       python3-pip \\
                       libtinfo-dev \\
                       clang-10 \\
                       wget \\
                       git \\
                       unzip \\
                       libxrandr-dev \\
                       libxinerama-dev \\
                       libxcursor-dev \\
                       libxi-dev \\
                       libglu1-mesa-dev \\
                       freeglut3-dev \\
                       mesa-common-dev \\
                       libssl-dev \\
                       libglm-dev \\
                       libxcb-keysyms1-dev \\
                       libxcb-dri3-dev \\
                       libxcb-randr0-dev \\
                       libxcb-ewmh-dev \\
                       libpng-dev \\
                       g++-multilib \\
                       libmirclient-dev \\
                       libwayland-dev \\
                       bison \\
                       libx11-xcb-dev \\
                       liblz4-dev \\
                       libzstd-dev \\
                       qt5-default \\
                       libglfw3 \\
                       libglfw3-dev \\
                       libjpeg-dev \\
                       libvulkan-dev
"""

NVIDIA_DRIVER_CAPABILITIES_BLOCK = """
ENV NVIDIA_DRIVER_CAPABILITIES compute,graphics,utility
"""

MAINTAINER_BLOCK = """
ENV DEBIAN_FRONTEND=noninteractive
LABEL maintainer="https://github.com/taichi-dev"
"""

CMAKE_BLOCK = """
# Install the latest version of CMAKE v3.20.5 from source
WORKDIR /
RUN wget https://github.com/Kitware/CMake/releases/download/v3.20.5/cmake-3.20.5-linux-x86_64.tar.gz
RUN tar xf cmake-3.20.5-linux-x86_64.tar.gz && \\
    rm cmake-3.20.5-linux-x86_64.tar.gz
ENV PATH="/cmake-3.20.5-linux-x86_64/bin:$PATH"
"""

LLVM_BLOCK = """
# Intall LLVM 10
WORKDIR /
# Make sure this URL gets updated each time there is a new prebuilt bin release
RUN wget https://github.com/taichi-dev/taichi_assets/releases/download/llvm10_linux_patch2/taichi-llvm-10.0.0-linux.zip
RUN unzip taichi-llvm-10.0.0-linux.zip && \\
    rm taichi-llvm-10.0.0-linux.zip
ENV PATH="/taichi-llvm-10.0.0-linux/bin:$PATH"
# Use Clang as the default compiler
ENV CC="clang-10"
ENV CXX="clang++-10"
"""

USER_BLOCK = """
# Create non-root user for running the container
RUN useradd -ms /bin/bash dev
WORKDIR /home/dev
USER dev
"""

VULKAN_BLOCK = """
# Setting up Vulkan SDK
# References
# [1] https://github.com/edowson/docker-nvidia-vulkan
# [2] https://gitlab.com/nvidia/container-images/vulkan/-/tree/master/docker
WORKDIR /vulkan
RUN wget https://sdk.lunarg.com/sdk/download/1.2.189.0/linux/vulkansdk-linux-x86_64-1.2.189.0.tar.gz
RUN tar xf vulkansdk-linux-x86_64-1.2.189.0.tar.gz && \\
    rm vulkansdk-linux-x86_64-1.2.189.0.tar.gz
# Locate Vulkan components
ENV VULKAN_SDK="/vulkan/1.2.189.0/x86_64"
ENV PATH="$VULKAN_SDK/bin:$PATH"
ENV LD_LIBRARY_PATH="$VULKAN_SDK/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
ENV VK_LAYER_PATH="$VULKAN_SDK/etc/vulkan/explicit_layer.d"
WORKDIR /usr/share/vulkan/icd.d
COPY ci/vulkan/icd.d/nvidia_icd.json nvidia_icd.json
"""

CONDA_BLOCK = """
# Install miniconda
RUN wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh && \\
    bash Miniconda3-latest-Linux-x86_64.sh -p /home/dev/miniconda -b
ENV PATH="/home/dev/miniconda/bin:$PATH"

# Set up multi-python environment
RUN conda init bash
RUN conda create -n py36 python=3.6 -y
RUN conda create -n py37 python=3.7 -y
RUN conda create -n py38 python=3.8 -y
RUN conda create -n py39 python=3.9 -y
"""

SCRIPTS_BLOCK = """
# Load scripts for build and test
WORKDIR /home/dev/scripts
COPY ci/scripts/{script} {script}

WORKDIR /home/dev
ENV LANG="C.UTF-8"
"""


class Parser(argparse.ArgumentParser):
    def error(self, message):
        """Make it print help message by default."""
        sys.stderr.write(f"error: {message}\n")
        self.print_help()
        sys.exit(2)


class AvailableColors(Enum):
    GRAY = 90
    RED = 91
    GREEN = 92
    YELLOW = 93
    BLUE = 94
    PURPLE = 95
    WHITE = 97
    BLACK = 30
    DEFAULT = 39


def _apply_color(color: str, message: str) -> str:
    """Dye message with color, fall back to default if it fails."""
    color_code = AvailableColors["DEFAULT"].value
    try:
        color_code = AvailableColors[color.upper()].value
    except KeyError:
        pass
    return f"\033[1;{color_code}m{message}\033[0m"


def info(message: str, plain=False):
    """Log the info to stdout"""
    print(_apply_color("default", message) if not plain else message)


def success(message: str):
    """Log the success to stdout"""
    print(_apply_color("green", f"[✔] {message}"))


def error(message: str):
    """Log the error to stderr"""
    print(_apply_color("red", f"[✗] {message}"), file=sys.stderr)


def warn(message: str):
    """Log the warning to stdout"""
    print(_apply_color("yellow", f"[!] {message}"))


def main(arguments=None):
    parser = Parser(description="""A CLI to generate Taichi CI Dockerfiles.
        Example usage:
            python3 Dockerfile_generator.py -o ubuntu -t cpu
        """)
    parser.add_argument(
        "-o",
        "--os",
        help="The target os of the Dockerfile.",
        required=True,
        type=str,
        choices=OS,
        metavar="\b",
    )
    parser.add_argument(
        "-t",
        "--target",
        help="The target hardware of the Dockerfile. [cpu/gpu]",
        required=True,
        type=str,
        choices=HARDWARE,
        metavar="\b",
    )
    args = parser.parse_args()

    pwd = Path(__file__).resolve().parent

    if args.target == "cpu":
        info("Generating Dockerfile(s) for CPU.")

        def f(os: str, version: str) -> str:
            info(f"OS: {os}, version: {version}")
            base_block = CPU_BASE_BLOCK.format(os=os, version=version)
            scripts_block = SCRIPTS_BLOCK.format(
                script=f"{os}_build_test_cpu.sh")
            install_block = CPU_APT_INSTALL_BLOCK

            # ubuntu 18.04 needs special treatments
            if os == "ubuntu" and version == "18.04":
                install_block = install_block.rstrip() + """ \\
                       zlib1g-dev"""

            dockerfile = reduce(
                lambda x, y: x + y,
                (base_block, MAINTAINER_BLOCK, install_block, CMAKE_BLOCK,
                 LLVM_BLOCK, USER_BLOCK, CONDA_BLOCK, scripts_block))
            filename = pwd / f"Dockerfile.{os}.{version}.cpu"
            info(f"Storing at: {filename}")
            with filename.open("w") as fp:
                fp.write(dockerfile)
    else:
        info("Generating Dockerfile(s) for GPU.")

        def f(os: str, version: str) -> str:
            info(f"OS: {os}, version: {version}")
            base_block = GPU_BASE_BLOCK.format(version=version)
            scripts_block = SCRIPTS_BLOCK.format(script=f"{os}_build_test.sh")
            install_block = GPU_APT_INSTALL_BLOCK

            # ubuntu 20.04 needs special treatments
            if os == "ubuntu" and version == "20.04":
                install_block = install_block.rstrip() + """ \\
                       vulkan-tools \\
                       vulkan-validationlayers-dev"""

            dockerfile = reduce(
                lambda x, y: x + y,
                (base_block, NVIDIA_DRIVER_CAPABILITIES_BLOCK,
                 MAINTAINER_BLOCK, install_block, CMAKE_BLOCK, LLVM_BLOCK,
                 VULKAN_BLOCK, USER_BLOCK, CONDA_BLOCK, scripts_block))
            filename = pwd / f"Dockerfile.{os}.{version}"
            info(f"Storing at: {filename}")
            with (filename).open("w") as fp:
                fp.write(dockerfile)

    list(map(functools.partial(f, args.os), OS[args.os]))
    success("Dockerfile generation is complete.")


if __name__ == "__main__":
    main()
