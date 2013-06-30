import os, os.path
from setuptools import setup

DIR = os.path.dirname(__file__)

with open(os.path.join(DIR, 'README.rst')) as f:
    README = f.read()

import chan

setup(
    name='chan',
    version=chan.__version__,
    description="Chan for Python, lovingly stolen from Go",
    author='Stuart Glaser',
    author_email='stuglaser@gmail.com',
    url='http://github.com/stuglaser/pychan',
    long_description=README,
    keywords='go chan channel select chanselect concurrency',
    license='BSD',
    packages=['chan'],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: BSD License',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Natural Language :: English',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 2 :: Only',
    ],
)
