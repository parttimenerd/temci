from setuptools import setup, find_packages
import temci.scripts.version as version
from os import path

here = path.abspath(path.dirname(__file__))

with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

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
        'click',
        'humanfriendly',
        'fn',
        'pyaml',
        'typing', 'seaborn', 'pytimeparse',
        'cairocffi',
        'matplotlib',
        'prompt_toolkit', 'ptpython',
        'cpuset-py3',
        'docopt',
        'jedi',
        'Pygments',
        'wcwidth',
        'rainbow_logging_handler',
        'tablib', 'glob2', 'globster'
    ],
    license='GPLv3',
    platforms='linux',
    classifiers=[
        'Programming Language :: Python :: 3.4',
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3 :: Only",
        "Operating System :: POSIX :: Linux",
        "Topic :: System :: Benchmark",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        'Intended Audience :: Developers',

    ],
    entry_points='''
        [console_scripts]
        temci=temci.scripts.cli:cli_with_error_catching
        temci_completion=temci.scripts.temci_completion:cli
    ''',
)