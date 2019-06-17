from os import path
import os

from setuptools import setup, find_packages

import temci.scripts.version as version

here = path.abspath(path.dirname(__file__))

with open(path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

non_minimal_deps = ['seaborn', 'cairocffi', 'matplotlib', 'prompt_toolkit', 'ptpython',
        'docopt', 'Pygments', 'typing', 'glob2', 'globster']

setup(
    name='temci',
    author="Johannes Bechberger",
    author_email="me@mostlynerdless.de",
    description='Advanced benchmarking tool',
    long_description=long_description,
    url="https://github.com/parttimenerd/temci",
    version=version.version,
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'click @ https://github.com/pallets/click/archive/f537a208591088499b388b06b2aca4efd5445119.zip',
        'humanfriendly', 'pytimeparse',
        'fn',
        'cpuset-py3',
        'wcwidth',
        'rainbow_logging_handler',
        'tablib',
        'pyyaml'
    ] + ([] if os.getenv("MINIMAL_TEMCI") == "1" else non_minimal_deps),
    tests_require=['pytest'] + ([] if os.getenv("MINIMAL_TEMCI") == "1" else ['pytest-clarity']),
    license='GPLv3',
    platforms='linux',
    classifiers=[
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3 :: Only",
        "Operating System :: POSIX :: Linux",
        "Topic :: System :: Benchmark",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        'Intended Audience :: Developers',

    ],
    entry_points='''
        [console_scripts]
        temci=temci.scripts.run:run
        temci_completion=temci.scripts.temci_completion:cli
    '''
)
