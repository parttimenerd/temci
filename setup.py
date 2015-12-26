from setuptools import setup, find_packages

setup(
    name='temci',
    version='0.1',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'Click',
        'humanfriendly',
        'fn',
        'pyaml',
        'typing', 'seaborn', 'pytimeparse',
        'path.py', 'matplotlib2tikz'
    ],
    entry_points='''
        [console_scripts]
        temci=temci.scripts.cli:cli_with_error_catching
    ''',
)