#!/usr/bin/python

from setuptools import setup

setup(
    name="volvooncall",
    version="0.7.11",
    description="Communicate with VOC",
    url="https://github.com/molobrakos/volvooncall",
    license="",
    author="Erik",
    author_email="error.errorsson@gmail.com",
    scripts=["voc"],
    py_modules=["volvooncall", "mqtt", "util", "dashboard"],
    provides=["volvooncall"],
    install_requires=list(open("requirements.txt").read().strip().split("\n")),
    extras_require={"console": ["docopt"]},
)
