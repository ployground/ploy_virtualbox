from setuptools import setup
import os


here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README.rst')).read()


version = "1.0b2"


setup(
    version=version,
    description="A plugin for ploy providing support for VMs using VirtualBox.",
    long_description=README + "\n\n",
    name="ploy_virtualbox",
    author='Florian Schulze',
    author_email='florian.schulze@gmx.net',
    license="BSD 3-Clause License",
    url='http://github.com/ployground/ploy_virtualbox',
    classifiers=[
        'Environment :: Console',
        'Intended Audience :: System Administrators',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.3',
        'Topic :: System :: Installation/Setup',
        'Topic :: System :: Systems Administration'],
    include_package_data=True,
    zip_safe=False,
    packages=['ploy_virtualbox'],
    install_requires=[
        'setuptools',
        'ploy >= 1.0rc10',
        'lazy'],
    entry_points="""
        [ploy.plugins]
        virtualbox = ploy_virtualbox:plugin
    """)
