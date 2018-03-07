#!/usr/bin/python

from setuptools import setup

setup(name="volvooncall",
      version='0.4.4',
      description="Communicate with VOC",
      url="https://github.com/molobrakos/volvooncall",
      license="",
      author="Erik",
      author_email="error.errorsson@gmail.com",
      scripts=["voc"],
      py_modules=["volvooncall"],
      provides=["volvooncall"],
      install_requires=[
          'requests'
      ],
      extras_require={
          'console':  ['docopt'],
      })
