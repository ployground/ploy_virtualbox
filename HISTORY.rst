Changelog
=========

1.1.0 - 2015-01-20
------------------

* Log info when starting an instance.
  [fschulze]

* Handle instances in ``aborted`` state.
  [fschulze]

* Print error output of commands on failures.
  [fschulze]

* Use new helper in ploy 1.0.2 to setup proxycommand.
  [fschulze]

* Added possibility to specify a remote instance to use for a virtualbox master.
  [fschulze]

* Added ability to reference disk images via external URL for virtualbox instances storage.
  [tomster]


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
