from setuptools import setup, find_packages
import temci.scripts.version as version

setup(
    name='temci',
    version=version.version,
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'Click',
        'humanfriendly',
        'fn',
        'pyaml',
        'typing', 'seaborn', 'pytimeparse',
        'ruamel.yaml',
        'pympler',
        'cairocffi',
        'matplotlib',
        'cgroupspy',
        'prompt_toolkit', 'ptpython',
        'cpuset-py3',
    ],
    classifiers=[
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3 :: Only",
        "Topic :: System :: Benchmark",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Operating System :: POSIX :: Linux",
    ],
    entry_points='''
        [console_scripts]
        temci=temci.scripts.cli:cli_with_error_catching
        temci_completion=temci.scripts.temci_completion:cli
    ''',
)