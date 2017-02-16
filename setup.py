#!/usr/bin/python

from setuptools import setup

setup(name="volvooncall",
      version='0.2.0',
      description="Communicate with VOC",
      url="https://github.com/molobrakos/volvooncall",
      license="",
      author="Erik",
      author_email="Erik",
      scripts=["voc"],
      py_modules=["volvooncall"],
      provides=["volvooncall"],
      install_requires=[
          'requests'
      ],
      extras_require={
          'console':  ['docopt'],
      })
