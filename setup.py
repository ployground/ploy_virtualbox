from setuptools import setup
import os


here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README.rst')).read()


version = "1.0b1"


setup(
    version=version,
    description="A plugin for mr.awsome providing support for VMs using VirtualBox.",
    long_description=README + "\n\n",
    name="mr.awsome.virtualbox",
    author='Florian Schulze',
    author_email='florian.schulze@gmx.net',
    url='http://github.com/fschulze/mr.awsome.virtualbox',
    include_package_data=True,
    zip_safe=False,
    packages=['mr', 'mr.awsome_virtualbox'],
    namespace_packages=['mr'],
    install_requires=[
        'setuptools',
        'mr.awsome >= 1.0rc8',
        'lazy'],
    entry_points="""
        [mr.awsome.plugins]
        virtualbox = mr.awsome_virtualbox:plugin
    """)
