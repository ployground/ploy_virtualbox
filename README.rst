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

  For ``medium`` there is an additional option ``vb-disk:NAME`` which refers to a `Disk section`_ called ``NAME``.

  Example::

      storage =
          --type dvddrive --medium ~/downloads/archives/mfsbsd-se-9.2-RELEASE-amd64.iso
          --medium vb-disk:boot

``hostonlyadapter``
  If there is a matching `Host only interface section`_, then that is evaluated.

.. _Disk section:

Disk sections
=============

These section allow you to describe how disks should be created.
You can set the ``size`` and ``variant`` options.
See ``VBoxManage createhd`` documentation for details.

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


Changelog
=========

1.1.0 - Unreleased
------------------

* Use new helper in ploy 1.0.2 to setup proxycommand.
  [fschulze]

* Added possibility to specify a remote instance to use for a virtualbox master.
  [fschulze]


1.0.0 - 2014-07-19
------------------

* Added documentation.
  [fschulze]

* Renamed ``vb-master`` to ``virtualbox``, so the uids of instances are nicer.
  [fschulze]

* Enable DHCP server when creating or modifying it.
  [fschulze]


1.0b4 - 2014-07-15
------------------

* Verify and if possible create host only interfaces and dhcpservers.
  [fschulze]

* Add support for instances that have manually been put into ``saved`` state.
  [fschulze]


1.0b3 - 2014-07-08
------------------

* Packaging and test fixes.
  [fschulze]


1.0b2 - 2014-07-04
------------------

* Python 3 compatibility.
  [fschulze]

* Renamed mr.awsome to ploy and mr.awsome.virtualbox to ploy_virtualbox.
  [fschulze]


1.0b1 - 2014-06-16
------------------

* Initial release
  [fschulze]
