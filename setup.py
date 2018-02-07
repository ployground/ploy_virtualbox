from setuptools import setup
import os


here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README.rst')).read()
HISTORY = open(os.path.join(here, 'HISTORY.rst')).read()


version = "2.0.0b1"


setup(
    version=version,
    description="Plugin for ploy to provision virtual machines using VirtualBox.",
    long_description=README + "\n\n" + HISTORY,
    name="ploy_virtualbox",
    author='Florian Schulze',
    author_email='florian.schulze@gmx.net',
    license="BSD 3-Clause License",
    url='http://github.com/ployground/ploy_virtualbox',
    classifiers=[
        'Environment :: Console',
        'Intended Audience :: System Administrators',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: System :: Installation/Setup',
        'Topic :: System :: Systems Administration'],
    include_package_data=True,
    zip_safe=False,
    packages=['ploy_virtualbox'],
    install_requires=[
        'setuptools',
        'ploy >= 2.0.0b1',
        'lazy'],
    python_requires='>=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*',
    entry_points="""
        [ploy.plugins]
        virtualbox = ploy_virtualbox:plugin
    """)
