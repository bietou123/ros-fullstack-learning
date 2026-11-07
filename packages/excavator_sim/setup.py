from glob import glob
import os

from setuptools import setup

package_name = "excavator_sim"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
        (os.path.join("share", package_name, "config"), glob("config/*")),
        # 只 glob 文件，不要 glob("urdf/*")：那会把 urdf/meshes 这个**目录**
        # 也放进 data_files，install_data 阶段报
        #   error: can't copy 'urdf\meshes': doesn't exist or not a regular file
        # 整个 colcon build 失败（不是警告）。
        (os.path.join("share", package_name, "urdf"),
         glob("urdf/*.urdf") + glob("urdf/*.xacro")),
        # OBJ 在 urdf/meshes/ 子目录里，glob("urdf/*") 只取一层文件、不会递归。
        # 少了这一行 `colcon build` 后 install/ 里没有 mesh，rviz 的 RobotModel
        # 全是空的（而且报错只出现在 rviz 控制台，构建照样成功 —— 静默丢失）。
        (os.path.join("share", package_name, "urdf", "meshes"),
         glob("urdf/meshes/*.obj") + glob("urdf/meshes/*.mtl")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="bietou123",
    maintainer_email="bietou123@users.noreply.github.com",
    description="922-class hydraulic excavator kinematic demo for rviz",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "excavator_anim = excavator_sim.anim_node:main",
        ],
    },
)
