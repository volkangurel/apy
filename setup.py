#!/usr/bin/env python3
from setuptools import setup, find_packages

setup(
    name='apy',
    version='0.1.0',

    author='Volkan Gurel',
    author_email='me@volkangurel.com',
    url='https://github.com/volkangurel/apy',

    packages=find_packages(),
    install_requires=[
        'django >= 1.5.1',
        'pytz',
        ],
    )
