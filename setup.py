'''
A C++ header (and source) parser.
'''
import glob
import os
import sys

import setuptools

README_PATH = 'README.md'
PLUGINS = 'pyheaders/plugins/*.so'

if os.path.exists(README_PATH):
    with open(README_PATH, 'r') as fd:
        LONG_DESCRIPTION = fd.read()

setuptools.setup(
    name='pyheaders',
    version='0.0.1',
    url='https://github.com/Roynecro97/pyheaders',
    project_urls={
        "Source Code": 'https://github.com/Roynecro97/pyheaders'
    },
    license='MIT License',
    author='',
    author_email='',
    description='C++ header (and source) parser',
    long_description=LONG_DESCRIPTION,
    long_description_content_type='text/markdown',
    install_requires=[],
    packages=setuptools.find_packages(exclude=['test']),
    data_files=[('plugins', glob.glob(PLUGINS))],
    zip_safe=False,  # Maybe True?
    include_package_data=True,
    platforms=['MacOS X', 'Posix'],
    test_suite='test',
    classifiers=[
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: POSIX',
        'Programming Language :: C++',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: Implementation :: CPython',
        'Development Status :: 2 - Pre-Alpha',
        'Topic :: Software Development',
        'Topic :: Software Development :: Libraries',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Utilities'
    ],
    entry_points={
        'console_scripts': [
            'pyheaders = pyheaders.__main__:main',
            f'pyheaders{sys.version_info.major} = pyheaders.__main__:main',
            f'pyheaders{sys.version_info.major}.{sys.version_info.minor} = pyheaders.__main__:main'
        ]
    }
)
