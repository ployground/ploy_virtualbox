Overview
========

The ploy_virtualbox plugin provides integration of `VirtualBox`_ with `ploy`_.

.. _VirtualBox: https://www.virtualbox.org
.. _ploy: https://github.com/ployground/


Installation
============

ploy_virtualbox is best installed with easy_install, pip or with zc.recipe.egg in a buildout.


Master
======

The default master for ploy_virtualbox is ``virtualbox`` and has the following options:

``headless``
  Whether to start instances in headless mode by default.
  If not set, the system default is used.

``use-acpi-powerbutton``
  Whether to use acpi power off by default when stopping instances.
  If not set, the system default is used.

``basefolder``
  The basefolder for VirtualBox data.
  If not set, the VirtualBox default is used.
  This varies depending on the OS that ploy is running in.
  When not provided as absolute path, then it's relative to ``ploy.conf``.

``instance``
  Name of instance to use to execute VirtualBox commands instead of the default local machine.

Example::

    [vb-master:virtualbox]
    headless = true


Instances
=========

``headless``
  Whether to start this instance in headless mode.
  If not set, the setting of the master is used.

``use-acpi-powerbutton``
  Whether to use acpi power off for this instance when stopping.
  If not set, the setting of the master is used.

``basefolder``
  The basefolder for this instances VirtualBox data.
  If not set, the setting of the master is used.
  When not provided as absolute path, then it's relative to ``ploy.conf``.

``no-terminate``
  If set to ``yes``, the instance can't be terminated via ploy until the setting is changed to ``no`` or removed entirely.

Any option starting with ``vm-`` is stripped of the ``vm-`` prefix and passed on to VBoxManage.
Almost all of these options are passed as is.
The following options are handled differently or have some convenience added:

``storage``
  One storage definition per line.
  See ``VBoxManage storageattach`` documentation for details.

  If you don't specify the ``type``, then ``hdd`` is used by default.

  You don't have to specify the ``port``, if not set the line number starting at zero is used.

  If you don't set ``--storagectl`` then ``sata`` is used as default and if that controller doesn't exist it's created automatically.

  If ``medium`` references a local file that path will be passed directly to ``VBoxManage storageattach``.

  If it takes the form ``vb-disk:NAME`` which refers to a `Disk section`_ called ``NAME`` that will be used instead.

  If it takes the form of an URL, the filename of that URL is assumed to be located at ``~/.ploy/downloads/`` (this default can be overridden in the ``[global]`` section of the configuration file with an entry ``download_dir``).
  If the file does not exist it will be downloaded.

  When using the URL notation it is strongly encouraged to also provide a checksum using the ``--medium_sha1`` key (currently only SHA1 is supported).

  Example for using a local ISO image as DVD drive::

      storage =
          --type dvddrive --medium ~/downloads/archives/mfsbsd-se-9.2-RELEASE-amd64.iso
          --medium vb-disk:boot

  Example for referencing an external URL::

      storage =
          --type dvddrive --medium http://mfsbsd.vx.sk/files/iso/11/amd64/mfsbsd-se-11.1-RELEASE-amd64.iso --medium_sha1 2fd80caf57c29d62859bccfa3b8ec7b5b244406e
          --medium vb-disk:boot

``hostonlyadapter``
  If there is a matching `Host only interface section`_, then that is evaluated.

.. _Disk section:

Disk sections
=============

These section allow you to describe how disks should be created.

You can set the ``size``, ``variant`` and ``format`` options as described in the ``VBoxManage createhd`` documentation.

The ``filename`` option allows you to set a filename for the disk, the extension is automatically added based on the ``format`` option.
If you use a relative path, then it's base is the ``basefolder`` setting of the instance.

When the ``delete`` option is set to ``false``, the disk is not deleted when the instance using it is terminated.
The default is to delete the disk upon instance termination.

Example::

  [vb-disk:boot]
  size = 102400


.. _Host only interface section:

Host only interface sections
============================

If you want to use host only network interfaces, then this allows you to make sure your settings are as expected and the interface exists.
For now only the ``ip`` option is supported.
See ``VBoxManage hostonlyif`` documentation for details.

Example::

  [vb-hostonlyif:vboxnet0]
  ip = 192.168.56.1


DHCP
----

If a ``vb-dhcpserver`` section with the same name exists, then it is checked and if needed configured as well.
See ``VBoxManage hostonlyif`` documentation for details.

Example::

  [vb-dhcpserver:vboxnet0]
  ip = 192.168.56.2
  netmask = 255.255.255.0
  lowerip = 192.168.56.100
  upperip = 192.168.56.254

The combination of ``vb-hostonlyif`` with ``vb-dhcpserver`` allows to configure a hostonly network with a deterministic IP address.
In the above example you could configure an instance with a static IP address of ``192.168.56.99`` which would be addressable from the host.
The important part is to chose an address that is *within* the DHCP server network but *outside* its DHCP pool, which is defined by ``lowerip`` and ``upperip`` respecitively.


SSH
===

Depending on the setup we can't get the IP address or host name automatically.

Unfortunately VirtualBox doesn't provide a way to see which instance got which IP address from it's own DHCP servers for example.

If you know which host name or ip address your instance will have, then set the ``host`` or ``ip`` option as explained above in the ``hostonly`` section.

As a workaround you can also setup a NAT port forwarding like this::

  vm-nic2 = nat
  vm-natpf2 = ssh,tcp,,47022,,22

For this case ploy_virtualbox knows how to get the port and uses it for SSH access via localhost.


If you install the VirtualBox guest additions in your instance, then the ``status`` command can show you the current IP address of the instance.


Example config
==============

::

  [vb-master:virtualbox]
  # use-acpi-powerbutton = false

  [vb-disk:boot]
  size = 102400

  [vb-hostonlyif:vboxnet0]
  ip = 192.168.56.1

  [vb-dhcpserver:vboxnet0]
  ip = 192.168.56.2
  netmask = 255.255.255.0
  lowerip = 192.168.56.100
  upperip = 192.168.56.254

  [vb-instance:foo]
  # headless = true
  vm-ostype = FreeBSD_64
  vm-memory = 512
  vm-accelerate3d = off
  vm-acpi = on
  vm-rtcuseutc = on
  vm-boot1 = disk
  vm-boot2 = dvd
  vm-nic1 = hostonly
  vm-hostonlyadapter1 = vboxnet0
  vm-nic2 = nat
  vm-natpf2 = ssh,tcp,,47022,,22
  storage =
      --type dvddrive --medium ~/downloads/archives/mfsbsd-se-9.2-RELEASE-amd64.iso
      --medium vb-disk:boot
