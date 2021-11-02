#!/usr/bin/python

from setuptools import setup

setup(
    name="volvooncall",
    version="0.9.1",
    description="Communicate with VOC",
    url="https://github.com/molobrakos/volvooncall",
    license="Unlicense",
    author="Erik",
    author_email="error.errorsson@gmail.com",
    scripts=["voc"],
    packages=["volvooncall"],
    install_requires=list(open("requirements.txt").read().strip().split("\n")),
    extras_require={"console": ["docopt"], "influxdb": ["influxdb"]},
)
