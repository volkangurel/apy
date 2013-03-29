#!/usr/bin/env python
from setuptools import setup, find_packages

setup(
    name='apy',
    version='0.1.0',

    author='Volkan Gurel',
    author_email='me@volkangurel.com',
    url='https://github.com/volkangurel/arzlan',

    packages=find_packages(),
    install_requires=[
        'django >= 1.5.1',
        ],
    )
