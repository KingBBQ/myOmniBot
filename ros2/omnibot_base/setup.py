from glob import glob

from setuptools import find_packages, setup

package_name = "omnibot_base"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="gregor",
    maintainer_email="gw@communitylabs.de",
    description="ROS2-Bruecke zum Motorknoten des Omnibot 5402",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "motor_node = omnibot_base.motor_node:main",
        ],
    },
)
