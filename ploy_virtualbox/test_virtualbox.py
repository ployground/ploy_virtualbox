from __future__ import unicode_literals
import logging
import os
import pytest


@pytest.yield_fixture(params=['vboxmanage4.txt', 'vboxmanage6.txt'])
def vbm_infos(request, tempdir):
    import pkg_resources
    path = tempdir.directory.encode('ascii')
    yield dict(
        systemproperties=b'Default machine folder:          %s' % path,
        usage=pkg_resources.resource_string(
            'ploy_virtualbox', request.param))


@pytest.yield_fixture
def popen_mock(monkeypatch):
    class Popen:
        def __init__(self, cmd_args, **kw):
            self.cmd_args = list(cmd_args)

        def communicate(self, input=None):
            try:
                expected = self.expect.pop(0)
            except IndexError:  # pragma: no cover - only on failures
                expected = (['VBoxManage'], 0, b'', b'')
            cmd_args, rc, out, err = expected
            assert self.cmd_args == cmd_args
            self.returncode = rc
            return (out, err)

    monkeypatch.setattr('subprocess.Popen', Popen)
    yield Popen


@pytest.yield_fixture
def ctrl(ployconf):
    from ploy import Controller
    import ploy_virtualbox
    ployconf.fill([
        '[vb-instance:foo]'])
    ctrl = Controller(configpath=ployconf.directory)
    ctrl.plugins = {'virtualbox': ploy_virtualbox.plugin}
    yield ctrl


def caplog_messages(caplog, level=logging.INFO):
    return [
        x.message
        for x in caplog.records
        if x.levelno >= level]


class VMInfo:
    def __init__(self):
        self._info = dict()
        self._info_updates = []
        self._nic = 1
        self._storagectl = 0

    def decode(self, encoding):
        return self

    def splitlines(self):
        self._info.update(self._info_updates.pop(0))
        return ["%s=%s" % (x, self._info[x]) for x in sorted(self._info)]

    def __call__(self):
        self._info_updates.append(dict())
        return self

    def nic(self, nictype):
        d = dict()
        d['nic%d' % self._nic] = "'%s'" % nictype
        self._info_updates.append(d)
        self._nic += 1
        return self

    def state(self, state):
        self._info_updates.append(dict(VMState="'%s'" % state))
        return self

    def storagectl(self, **kw):
        d = dict()
        for k, v in kw.items():
            d['storagecontroller%s%d' % (k, self._storagectl)] = "'%s'" % v
        self._info_updates.append(d)
        self._storagectl += 1
        return self


def test_start(ctrl, popen_mock, tempdir, vbm_infos, caplog):
    import uuid
    uid = str(uuid.uuid4()).encode('ascii')
    vminfo = VMInfo()
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, b'', b''),
        (['VBoxManage'], 0, vbm_infos['usage'], b''),
        (['VBoxManage', 'list', 'systemproperties'], 0, vbm_infos['systemproperties'], b''),
        (['VBoxManage', 'createvm', '--name', 'foo', '--basefolder', tempdir.directory, '--ostype', 'Other', '--register'], 0, b'', b''),
        (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'startvm', 'foo'], 0, b'', b'')]
    ctrl(['./bin/ploy', 'start', 'foo'])
    assert popen_mock.expect == []
    assert caplog_messages(caplog) == [
        "Creating instance 'foo'",
        "Starting instance 'vb-instance:foo'",
        "Instance started"]


def test_start_status(ctrl, ployconf, popen_mock, tempdir, vbm_infos, caplog):
    import uuid
    uid = str(uuid.uuid4()).encode('ascii')
    ployconf.fill([
        '[vb-instance:foo]',
        'vm-nic1 = hostonly'])
    vminfo = VMInfo()
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, b'', b''),
        (['VBoxManage'], 0, vbm_infos['usage'], b''),
        (['VBoxManage', 'list', 'systemproperties'], 0, vbm_infos['systemproperties'], b''),
        (['VBoxManage', 'createvm', '--name', 'foo', '--basefolder', tempdir.directory, '--ostype', 'Other', '--register'], 0, b'', b''),
        (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), b''),
        (['VBoxManage', 'modifyvm', 'foo', '--nic1', 'hostonly'], 0, b'', b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.nic('hostonly'), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'startvm', 'foo'], 0, b'', b''),
        (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('running'), b''),
        (['VBoxManage', 'guestproperty', 'enumerate', 'foo'], 0, b'Name: /VirtualBox/GuestInfo/Net/0/V4/IP, value: 192.168.56.3, timestamp: 1, flags: ', b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b'')]
    ctrl(['./bin/ploy', 'start', 'foo'])
    ctrl(['./bin/ploy', 'status', 'foo'])
    assert popen_mock.expect == []
    assert caplog_messages(caplog) == [
        "Creating instance 'foo'",
        "Starting instance 'vb-instance:foo'",
        "Instance started",
        "IP for hostonly interface: 192.168.56.3",
        "Instance running."]


def test_start_stop(ctrl, popen_mock, tempdir, vbm_infos, caplog):
    import uuid
    uid = str(uuid.uuid4()).encode('ascii')
    vminfo = VMInfo()
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, b'', b''),
        (['VBoxManage'], 0, vbm_infos['usage'], b''),
        (['VBoxManage', 'list', 'systemproperties'], 0, vbm_infos['systemproperties'], b''),
        (['VBoxManage', 'createvm', '--name', 'foo', '--basefolder', tempdir.directory, '--ostype', 'Other', '--register'], 0, b'', b''),
        (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'startvm', 'foo'], 0, b'', b''),
        (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('running'), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'controlvm', 'foo', 'poweroff'], 0, b'', b'')]
    ctrl(['./bin/ploy', 'start', 'foo'])
    ctrl(['./bin/ploy', 'stop', 'foo'])
    assert popen_mock.expect == []
    assert caplog_messages(caplog) == [
        "Creating instance 'foo'",
        "Starting instance 'vb-instance:foo'",
        "Instance started",
        "Stopping instance 'foo'",
        "Stopping instance by sending 'poweroff'.",
        "Instance stopped"]


def test_start_stop_stop(ctrl, popen_mock, tempdir, vbm_infos, caplog):
    import uuid
    uid = str(uuid.uuid4()).encode('ascii')
    vminfo = VMInfo()
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, b'', b''),
        (['VBoxManage'], 0, vbm_infos['usage'], b''),
        (['VBoxManage', 'list', 'systemproperties'], 0, vbm_infos['systemproperties'], b''),
        (['VBoxManage', 'createvm', '--name', 'foo', '--basefolder', tempdir.directory, '--ostype', 'Other', '--register'], 0, b'', b''),
        (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'startvm', 'foo'], 0, b'', b''),
        (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('running'), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'controlvm', 'foo', 'poweroff'], 0, b'', b''),
        (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), b'')]
    ctrl(['./bin/ploy', 'start', 'foo'])
    ctrl(['./bin/ploy', 'stop', 'foo'])
    ctrl(['./bin/ploy', 'stop', 'foo'])
    assert popen_mock.expect == []
    assert caplog_messages(caplog) == [
        "Creating instance 'foo'",
        "Starting instance 'vb-instance:foo'",
        "Instance started",
        "Stopping instance 'foo'",
        "Stopping instance by sending 'poweroff'.",
        "Instance stopped",
        "Instance state: stopped",
        "Instance not stopped"]


def test_start_stop_status(ctrl, popen_mock, tempdir, vbm_infos, caplog):
    import uuid
    uid = str(uuid.uuid4()).encode('ascii')
    vminfo = VMInfo()
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, b'', b''),
        (['VBoxManage'], 0, vbm_infos['usage'], b''),
        (['VBoxManage', 'list', 'systemproperties'], 0, vbm_infos['systemproperties'], b''),
        (['VBoxManage', 'createvm', '--name', 'foo', '--basefolder', tempdir.directory, '--ostype', 'Other', '--register'], 0, b'', b''),
        (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'startvm', 'foo'], 0, b'', b''),
        (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('running'), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'controlvm', 'foo', 'poweroff'], 0, b'', b''),
        (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), b'')]
    ctrl(['./bin/ploy', 'start', 'foo'])
    ctrl(['./bin/ploy', 'stop', 'foo'])
    ctrl(['./bin/ploy', 'status', 'foo'])
    assert popen_mock.expect == []
    assert caplog_messages(caplog) == [
        "Creating instance 'foo'",
        "Starting instance 'vb-instance:foo'",
        "Instance started",
        "Stopping instance 'foo'",
        "Stopping instance by sending 'poweroff'.",
        "Instance stopped",
        "Instance state: stopped"]


def test_start_stop_acpi(ctrl, popen_mock, tempdir, vbm_infos, caplog):
    import uuid
    uid = str(uuid.uuid4()).encode('ascii')
    vminfo = VMInfo()
    vminfo._info['acpi'] = '"on"'
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, b'', b''),
        (['VBoxManage'], 0, vbm_infos['usage'], b''),
        (['VBoxManage', 'list', 'systemproperties'], 0, vbm_infos['systemproperties'], b''),
        (['VBoxManage', 'createvm', '--name', 'foo', '--basefolder', tempdir.directory, '--ostype', 'Other', '--register'], 0, b'', b''),
        (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'startvm', 'foo'], 0, b'', b''),
        (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('running'), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'controlvm', 'foo', 'acpipowerbutton'], 0, b'', b''),
        (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('stopping'), b''),
        (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), b'')]
    ctrl(['./bin/ploy', 'start', 'foo'])
    ctrl(['./bin/ploy', 'stop', 'foo'])
    assert popen_mock.expect == []
    assert caplog_messages(caplog) == [
        "Creating instance 'foo'",
        "Starting instance 'vb-instance:foo'",
        "Instance started",
        "Stopping instance 'foo'",
        "Trying to stop instance with ACPI:",
        "Instance stopped"]


def test_start_stop_acpi_force(ctrl, popen_mock, tempdir, vbm_infos, monkeypatch, caplog):
    import uuid
    uid = str(uuid.uuid4()).encode('ascii')
    vminfo = VMInfo()
    vminfo._info['acpi'] = '"on"'
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, b'', b''),
        (['VBoxManage'], 0, vbm_infos['usage'], b''),
        (['VBoxManage', 'list', 'systemproperties'], 0, vbm_infos['systemproperties'], b''),
        (['VBoxManage', 'createvm', '--name', 'foo', '--basefolder', tempdir.directory, '--ostype', 'Other', '--register'], 0, b'', b''),
        (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'startvm', 'foo'], 0, b'', b''),
        (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('running'), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'controlvm', 'foo', 'acpipowerbutton'], 0, b'', b''),
        (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b'')]
    for i in range(59):
        popen_mock.expect.extend([
            (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
            (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b'')])
    popen_mock.expect.append((['VBoxManage', 'controlvm', 'foo', 'poweroff'], 0, b'', b''))
    monkeypatch.setattr('time.sleep', lambda d: None)
    ctrl(['./bin/ploy', 'start', 'foo'])
    ctrl(['./bin/ploy', 'stop', 'foo'])
    assert popen_mock.expect == []
    assert caplog_messages(caplog) == [
        "Creating instance 'foo'",
        "Starting instance 'vb-instance:foo'",
        "Instance started",
        "Stopping instance 'foo'",
        "Trying to stop instance with ACPI:",
        "Stopping instance by sending 'poweroff'.",
        "Instance stopped"]


def test_start_terminate(ctrl, popen_mock, tempdir, vbm_infos, yesno_mock, caplog):
    import uuid
    uid = str(uuid.uuid4()).encode('ascii')
    vminfo = VMInfo()
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, b'', b''),
        (['VBoxManage'], 0, vbm_infos['usage'], b''),
        (['VBoxManage', 'list', 'systemproperties'], 0, vbm_infos['systemproperties'], b''),
        (['VBoxManage', 'createvm', '--name', 'foo', '--basefolder', tempdir.directory, '--ostype', 'Other', '--register'], 0, b'', b''),
        (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'startvm', 'foo'], 0, b'', b''),
        (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('running'), b''),
        (['VBoxManage', 'controlvm', 'foo', 'poweroff'], 0, b'', b''),
        (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), b''),
        (['VBoxManage', 'unregistervm', 'foo', '--delete'], 0, b'', b'')]
    yesno_mock.expected = [
        ("Are you sure you want to terminate 'vb-instance:foo'?", True)]
    ctrl(['./bin/ploy', 'start', 'foo'])
    ctrl(['./bin/ploy', 'terminate', 'foo'])
    assert popen_mock.expect == []
    assert caplog_messages(caplog) == [
        "Creating instance 'foo'",
        "Starting instance 'vb-instance:foo'",
        "Instance started",
        "Stopping instance 'foo'",
        "Waiting for instance to stop",
        "Terminating instance 'foo'",
        "Instance terminated"]


def test_start_stop_terminate(ctrl, popen_mock, tempdir, vbm_infos, yesno_mock, caplog):
    import uuid
    uid = str(uuid.uuid4()).encode('ascii')
    vminfo = VMInfo()
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, b'', b''),
        (['VBoxManage'], 0, vbm_infos['usage'], b''),
        (['VBoxManage', 'list', 'systemproperties'], 0, vbm_infos['systemproperties'], b''),
        (['VBoxManage', 'createvm', '--name', 'foo', '--basefolder', tempdir.directory, '--ostype', 'Other', '--register'], 0, b'', b''),
        (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'startvm', 'foo'], 0, b'', b''),
        (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('running'), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'controlvm', 'foo', 'poweroff'], 0, b'', b''),
        (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), b''),
        (['VBoxManage', 'unregistervm', 'foo', '--delete'], 0, b'', b'')]
    yesno_mock.expected = [
        ("Are you sure you want to terminate 'vb-instance:foo'?", True)]
    ctrl(['./bin/ploy', 'start', 'foo'])
    ctrl(['./bin/ploy', 'stop', 'foo'])
    ctrl(['./bin/ploy', 'terminate', 'foo'])
    assert popen_mock.expect == []
    assert caplog_messages(caplog) == [
        "Creating instance 'foo'",
        "Starting instance 'vb-instance:foo'",
        "Instance started",
        "Stopping instance 'foo'",
        "Stopping instance by sending 'poweroff'.",
        "Instance stopped",
        "Terminating instance 'foo'",
        "Instance terminated"]


def test_start_with_hdd(ctrl, ployconf, popen_mock, tempdir, vbm_infos, caplog):
    import uuid
    uid = str(uuid.uuid4()).encode('ascii')
    ployconf.fill([
        '[vb-disk:boot]',
        'size = 102400',
        '[vb-instance:foo]',
        'storage = --medium vb-disk:boot'])
    vminfo = VMInfo()
    boot_vdi = os.path.join(tempdir.directory, 'foo', 'boot.vdi')
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, b'', b''),
        (['VBoxManage'], 0, vbm_infos['usage'], b''),
        (['VBoxManage', 'list', 'systemproperties'], 0, vbm_infos['systemproperties'], b''),
        (['VBoxManage', 'createvm', '--name', 'foo', '--basefolder', tempdir.directory, '--ostype', 'Other', '--register'], 0, b'', b''),
        (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'storagectl', 'foo', '--name', 'sata', '--add', 'sata'], 0, b'', b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.storagectl(name='sata'), b''),
        (['VBoxManage', 'createhd', '--filename', boot_vdi, '--format', 'VDI', '--size', '102400'], 0, b'', b''),
        (['VBoxManage', 'storageattach', 'foo', '--medium', boot_vdi, '--port', '0', '--storagectl', 'sata', '--type', 'hdd'], 0, b'', b''),
        (['VBoxManage', 'startvm', 'foo'], 0, b'', b'')]
    ctrl(['./bin/ploy', 'start', 'foo'])
    assert popen_mock.expect == []
    assert caplog_messages(caplog) == [
        "Creating instance 'foo'",
        "Adding default 'sata' controller.",
        "Starting instance 'vb-instance:foo'",
        "Instance started"]


def test_start_with_dvd(ctrl, ployconf, popen_mock, tempdir, vbm_infos, caplog):
    import uuid
    uid = str(uuid.uuid4()).encode('ascii')
    ployconf.fill([
        '[vb-disk:boot]',
        'size = 102400',
        '[vb-instance:foo]',
        'storage = --type dvddrive --medium mfsbsd.iso'])
    vminfo = VMInfo()
    medium = os.path.join(ployconf.directory, 'mfsbsd.iso')
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, b'', b''),
        (['VBoxManage'], 0, vbm_infos['usage'], b''),
        (['VBoxManage', 'list', 'systemproperties'], 0, vbm_infos['systemproperties'], b''),
        (['VBoxManage', 'createvm', '--name', 'foo', '--basefolder', tempdir.directory, '--ostype', 'Other', '--register'], 0, b'', b''),
        (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'storagectl', 'foo', '--name', 'sata', '--add', 'sata'], 0, b'', b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.storagectl(name='sata'), b''),
        (['VBoxManage', 'storageattach', 'foo', '--medium', medium, '--port', '0', '--storagectl', 'sata', '--type', 'dvddrive'], 0, b'', b''),
        (['VBoxManage', 'startvm', 'foo'], 0, b'', b'')]
    ctrl(['./bin/ploy', 'start', 'foo'])
    assert popen_mock.expect == []
    assert caplog_messages(caplog) == [
        "Creating instance 'foo'",
        "Adding default 'sata' controller.",
        "Starting instance 'vb-instance:foo'",
        "Instance started"]


def test_status(ctrl, popen_mock, caplog):
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, b'', b'')]
    ctrl(['./bin/ploy', 'status', 'foo'])
    assert popen_mock.expect == []
    assert caplog_messages(caplog) == [
        "Instance 'foo' unavailable"]


def test_stop(ctrl, popen_mock, caplog):
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, b'', b'')]
    ctrl(['./bin/ploy', 'stop', 'foo'])
    assert popen_mock.expect == []
    assert caplog_messages(caplog) == [
        "Instance 'foo' unavailable"]


def test_terminate(ctrl, popen_mock, yesno_mock, caplog):
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, b'', b'')]
    yesno_mock.expected = [
        ("Are you sure you want to terminate 'vb-instance:foo'?", True)]
    ctrl(['./bin/ploy', 'terminate', 'foo'])
    assert popen_mock.expect == []
    assert caplog_messages(caplog) == [
        "Instance 'foo' unavailable"]


def test_dhcpserver(ctrl, ployconf, popen_mock, tempdir, vbm_infos, caplog):
    import uuid
    uid = str(uuid.uuid4()).encode('ascii')
    hoifuid = str(uuid.uuid4()).encode('ascii')
    ployconf.fill([
        '[vb-dhcpserver:vboxnet0]',
        'ip = 192.168.56.2',
        'netmask = 255.255.255.0',
        'lowerip = 192.168.56.100',
        'upperip = 192.168.56.254',
        '[vb-hostonlyif:vboxnet0]',
        'ip = 192.168.56.1',
        '[vb-instance:foo]',
        'vm-nic1 = hostonly',
        'vm-hostonlyadapter1 = vboxnet0'])
    vminfo = VMInfo()
    hostonlyif = b"\n".join([
        b"Name:            vboxnet0",
        b"GUID:            %s" % hoifuid,
        b"DHCP:            Disabled",
        b"IPAddress:       192.168.56.1",
        b"NetworkMask:     255.255.255.0",
        b"IPV6Address:     ",
        b"IPV6NetworkMaskPrefixLength: 0",
        b"HardwareAddress: 0a:00:27:00:00:00",
        b"MediumType:      Ethernet",
        b"Wireless:        No",
        b"Status:          Down",
        b"VBoxNetworkName: HostInterfaceNetworking-vboxnet0",
        b"",
        b""])
    dhcpservers = b"\n".join([
        b"NetworkName:    HostInterfaceNetworking-vboxnet0",
        b"Dhcpd IP:       192.168.56.2",
        b"LowerIPAddress: 192.168.56.100",
        b"UpperIPAddress: 192.168.56.254",
        b"NetworkMask:    255.255.255.0",
        b"Enabled:        Yes",
        b"Global Configuration:",
        b"    minLeaseTime:     default",
        b"    defaultLeaseTime: default",
        b"    maxLeaseTime:     default",
        b"    Forced options:   None",
        b"    Suppressed opts.: None",
        b"        1/legacy: 255.255.255.0",
        b"Groups:               None",
        b"Individual Configs:   None",
        b"",
        b""])
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, b'', b''),
        (['VBoxManage'], 0, vbm_infos['usage'], b''),
        (['VBoxManage', 'list', 'systemproperties'], 0, vbm_infos['systemproperties'], b''),
        (['VBoxManage', 'createvm', '--name', 'foo', '--basefolder', tempdir.directory, '--ostype', 'Other', '--register'], 0, b'', b''),
        (['VBoxManage', 'list', 'vms'], 0, b'"foo" {%s}' % uid, b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), b''),
        (['VBoxManage', 'list', 'hostonlyifs'], 0, b'', b''),
        (['VBoxManage', 'hostonlyif', 'create'], 0, b'', b''),
        (['VBoxManage', 'list', 'hostonlyifs'], 0, hostonlyif, b''),
        (['VBoxManage', 'hostonlyif', 'ipconfig', 'vboxnet0', '--ip', '192.168.56.1'], 0, hostonlyif, b''),
        (['VBoxManage', 'list', 'dhcpservers'], 0, b'', b''),
        (['VBoxManage', 'dhcpserver', 'add', '--enable', '--ip', '192.168.56.2', '--lowerip', '192.168.56.100', '--netmask', '255.255.255.0', '--netname', 'HostInterfaceNetworking-vboxnet0', '--upperip', '192.168.56.254'], 0, b'', b''),
        (['VBoxManage', 'list', 'dhcpservers'], 0, dhcpservers, b''),
        (['VBoxManage', 'modifyvm', 'foo', '--hostonlyadapter1', 'vboxnet0', '--nic1', 'hostonly'], 0, b'', b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.nic('hostonly'), b''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), b''),
        (['VBoxManage', 'startvm', 'foo'], 0, b'', b'')]
    ctrl(['./bin/ploy', 'start', 'foo'])
    assert popen_mock.expect == []
    assert caplog_messages(caplog) == [
        "Creating instance 'foo'",
        "Created host only interface 'vboxnet0'.",
        "Added dhcpserver 'vboxnet0'.",
        "Starting instance 'vb-instance:foo'",
        "Instance started"]
