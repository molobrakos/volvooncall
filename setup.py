#!/usr/bin/python

from setuptools import setup

setup(
    name="volvooncall",
    version="0.9.2",
    description="Communicate with VOC",
    url="https://github.com/molobrakos/volvooncall",
    license="Unlicense",
    author="Erik",
    author_email="error.errorsson@gmail.com",
    scripts=["voc"],
    packages=["volvooncall"],
    install_requires=list(open("requirements.txt").read().strip().split("\n")),
    extras_require={
        "console": ["certifi", "docopt", "geopy>=1.14.0"],
        "mqtt": ["amqtt>=0.10.0,<0.11.0", "certifi"]
    },
    python_requires=">=3.8"
)
