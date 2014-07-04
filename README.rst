Example config
==============

::

  [vb-master:virtualbox]
  # use-acpi-powerbutton = false

  [vb-disk:boot]
  size = 102400

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
