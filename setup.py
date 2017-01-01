#!/usr/bin/python

from setuptools import setup
from volvooncall import __version__

setup(name="volvooncall",
      version=__version__,
      description="Communicate with VOC",
      url="https://github.com/molobrakos/volvooncall",
      license="",
      author="Erik",
      author_email="Erik",
      scripts=["voc"],
      py_modules=["volvooncall"],
      provides=["volvooncall"],)
