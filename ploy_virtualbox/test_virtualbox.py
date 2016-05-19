from __future__ import unicode_literals
import logging
import os
import pytest


@pytest.yield_fixture
def vbm_infos(tempdir):
    import pkg_resources
    yield dict(
        systemproperties='Default machine folder:          %s' % tempdir.directory,
        usage=pkg_resources.resource_string(
            'ploy_virtualbox', 'vboxmanage.txt'))


@pytest.yield_fixture
def popen_mock(monkeypatch):
    class Popen:
        def __init__(self, cmd_args, **kw):
            self.cmd_args = list(cmd_args)

        def communicate(self, input=None):
            try:
                expected = self.expect.pop(0)
            except IndexError:  # pragma: no cover - only on failures
                expected = (['VBoxManage'], 0, '', '')
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
    uid = str(uuid.uuid4())
    vminfo = VMInfo()
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, '', ''),
        (['VBoxManage'], 0, vbm_infos['usage'], ''),
        (['VBoxManage', 'list', 'systemproperties'], 0, vbm_infos['systemproperties'], ''),
        (['VBoxManage', 'createvm', '--name', 'foo', '--basefolder', tempdir.directory, '--ostype', 'Other', '--register'], 0, '', ''),
        (['VBoxManage', 'list', 'vms'], 0, '"foo" {%s}' % uid, ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), ''),
        (['VBoxManage', 'startvm', 'foo'], 0, '', '')]
    ctrl(['./bin/ploy', 'start', 'foo'])
    assert popen_mock.expect == []
    assert caplog_messages(caplog) == [
        "Creating instance 'foo'",
        "Starting instance 'vb-instance:foo'",
        "Instance started"]


def test_start_status(ctrl, ployconf, popen_mock, tempdir, vbm_infos, caplog):
    import uuid
    uid = str(uuid.uuid4())
    ployconf.fill([
        '[vb-instance:foo]',
        'vm-nic1 = hostonly'])
    vminfo = VMInfo()
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, '', ''),
        (['VBoxManage'], 0, vbm_infos['usage'], ''),
        (['VBoxManage', 'list', 'systemproperties'], 0, vbm_infos['systemproperties'], ''),
        (['VBoxManage', 'createvm', '--name', 'foo', '--basefolder', tempdir.directory, '--ostype', 'Other', '--register'], 0, '', ''),
        (['VBoxManage', 'list', 'vms'], 0, '"foo" {%s}' % uid, ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), ''),
        (['VBoxManage', 'modifyvm', 'foo', '--nic1', 'hostonly'], 0, '', ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.nic('hostonly'), ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), ''),
        (['VBoxManage', 'startvm', 'foo'], 0, '', ''),
        (['VBoxManage', 'list', 'vms'], 0, '"foo" {%s}' % uid, ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('running'), ''),
        (['VBoxManage', 'guestproperty', 'enumerate', 'foo'], 0, 'Name: /VirtualBox/GuestInfo/Net/0/V4/IP, value: 192.168.56.3, timestamp: 1, flags: ', ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), '')]
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
    uid = str(uuid.uuid4())
    vminfo = VMInfo()
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, '', ''),
        (['VBoxManage'], 0, vbm_infos['usage'], ''),
        (['VBoxManage', 'list', 'systemproperties'], 0, vbm_infos['systemproperties'], ''),
        (['VBoxManage', 'createvm', '--name', 'foo', '--basefolder', tempdir.directory, '--ostype', 'Other', '--register'], 0, '', ''),
        (['VBoxManage', 'list', 'vms'], 0, '"foo" {%s}' % uid, ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), ''),
        (['VBoxManage', 'startvm', 'foo'], 0, '', ''),
        (['VBoxManage', 'list', 'vms'], 0, '"foo" {%s}' % uid, ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('running'), ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), ''),
        (['VBoxManage', 'controlvm', 'foo', 'poweroff'], 0, '', '')]
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
    uid = str(uuid.uuid4())
    vminfo = VMInfo()
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, '', ''),
        (['VBoxManage'], 0, vbm_infos['usage'], ''),
        (['VBoxManage', 'list', 'systemproperties'], 0, vbm_infos['systemproperties'], ''),
        (['VBoxManage', 'createvm', '--name', 'foo', '--basefolder', tempdir.directory, '--ostype', 'Other', '--register'], 0, '', ''),
        (['VBoxManage', 'list', 'vms'], 0, '"foo" {%s}' % uid, ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), ''),
        (['VBoxManage', 'startvm', 'foo'], 0, '', ''),
        (['VBoxManage', 'list', 'vms'], 0, '"foo" {%s}' % uid, ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('running'), ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), ''),
        (['VBoxManage', 'controlvm', 'foo', 'poweroff'], 0, '', ''),
        (['VBoxManage', 'list', 'vms'], 0, '"foo" {%s}' % uid, ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), '')]
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
    uid = str(uuid.uuid4())
    vminfo = VMInfo()
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, '', ''),
        (['VBoxManage'], 0, vbm_infos['usage'], ''),
        (['VBoxManage', 'list', 'systemproperties'], 0, vbm_infos['systemproperties'], ''),
        (['VBoxManage', 'createvm', '--name', 'foo', '--basefolder', tempdir.directory, '--ostype', 'Other', '--register'], 0, '', ''),
        (['VBoxManage', 'list', 'vms'], 0, '"foo" {%s}' % uid, ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), ''),
        (['VBoxManage', 'startvm', 'foo'], 0, '', ''),
        (['VBoxManage', 'list', 'vms'], 0, '"foo" {%s}' % uid, ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('running'), ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), ''),
        (['VBoxManage', 'controlvm', 'foo', 'poweroff'], 0, '', ''),
        (['VBoxManage', 'list', 'vms'], 0, '"foo" {%s}' % uid, ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), '')]
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
    uid = str(uuid.uuid4())
    vminfo = VMInfo()
    vminfo._info['acpi'] = '"on"'
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, '', ''),
        (['VBoxManage'], 0, vbm_infos['usage'], ''),
        (['VBoxManage', 'list', 'systemproperties'], 0, vbm_infos['systemproperties'], ''),
        (['VBoxManage', 'createvm', '--name', 'foo', '--basefolder', tempdir.directory, '--ostype', 'Other', '--register'], 0, '', ''),
        (['VBoxManage', 'list', 'vms'], 0, '"foo" {%s}' % uid, ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), ''),
        (['VBoxManage', 'startvm', 'foo'], 0, '', ''),
        (['VBoxManage', 'list', 'vms'], 0, '"foo" {%s}' % uid, ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('running'), ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), ''),
        (['VBoxManage', 'controlvm', 'foo', 'acpipowerbutton'], 0, '', ''),
        (['VBoxManage', 'list', 'vms'], 0, '"foo" {%s}' % uid, ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('stopping'), ''),
        (['VBoxManage', 'list', 'vms'], 0, '"foo" {%s}' % uid, ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), '')]
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
    uid = str(uuid.uuid4())
    vminfo = VMInfo()
    vminfo._info['acpi'] = '"on"'
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, '', ''),
        (['VBoxManage'], 0, vbm_infos['usage'], ''),
        (['VBoxManage', 'list', 'systemproperties'], 0, vbm_infos['systemproperties'], ''),
        (['VBoxManage', 'createvm', '--name', 'foo', '--basefolder', tempdir.directory, '--ostype', 'Other', '--register'], 0, '', ''),
        (['VBoxManage', 'list', 'vms'], 0, '"foo" {%s}' % uid, ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), ''),
        (['VBoxManage', 'startvm', 'foo'], 0, '', ''),
        (['VBoxManage', 'list', 'vms'], 0, '"foo" {%s}' % uid, ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('running'), ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), ''),
        (['VBoxManage', 'controlvm', 'foo', 'acpipowerbutton'], 0, '', ''),
        (['VBoxManage', 'list', 'vms'], 0, '"foo" {%s}' % uid, ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), '')]
    for i in range(59):
        popen_mock.expect.extend([
            (['VBoxManage', 'list', 'vms'], 0, '"foo" {%s}' % uid, ''),
            (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), '')])
    popen_mock.expect.append((['VBoxManage', 'controlvm', 'foo', 'poweroff'], 0, '', ''))
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
    uid = str(uuid.uuid4())
    vminfo = VMInfo()
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, '', ''),
        (['VBoxManage'], 0, vbm_infos['usage'], ''),
        (['VBoxManage', 'list', 'systemproperties'], 0, vbm_infos['systemproperties'], ''),
        (['VBoxManage', 'createvm', '--name', 'foo', '--basefolder', tempdir.directory, '--ostype', 'Other', '--register'], 0, '', ''),
        (['VBoxManage', 'list', 'vms'], 0, '"foo" {%s}' % uid, ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), ''),
        (['VBoxManage', 'startvm', 'foo'], 0, '', ''),
        (['VBoxManage', 'list', 'vms'], 0, '"foo" {%s}' % uid, ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('running'), ''),
        (['VBoxManage', 'controlvm', 'foo', 'poweroff'], 0, '', ''),
        (['VBoxManage', 'list', 'vms'], 0, '"foo" {%s}' % uid, ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), ''),
        (['VBoxManage', 'unregistervm', 'foo', '--delete'], 0, '', '')]
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
    uid = str(uuid.uuid4())
    vminfo = VMInfo()
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, '', ''),
        (['VBoxManage'], 0, vbm_infos['usage'], ''),
        (['VBoxManage', 'list', 'systemproperties'], 0, vbm_infos['systemproperties'], ''),
        (['VBoxManage', 'createvm', '--name', 'foo', '--basefolder', tempdir.directory, '--ostype', 'Other', '--register'], 0, '', ''),
        (['VBoxManage', 'list', 'vms'], 0, '"foo" {%s}' % uid, ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), ''),
        (['VBoxManage', 'startvm', 'foo'], 0, '', ''),
        (['VBoxManage', 'list', 'vms'], 0, '"foo" {%s}' % uid, ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('running'), ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), ''),
        (['VBoxManage', 'controlvm', 'foo', 'poweroff'], 0, '', ''),
        (['VBoxManage', 'list', 'vms'], 0, '"foo" {%s}' % uid, ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), ''),
        (['VBoxManage', 'unregistervm', 'foo', '--delete'], 0, '', '')]
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
    uid = str(uuid.uuid4())
    ployconf.fill([
        '[vb-disk:boot]',
        'size = 102400',
        '[vb-instance:foo]',
        'storage = --medium vb-disk:boot'])
    vminfo = VMInfo()
    boot_vdi = os.path.join(tempdir.directory, 'foo', 'boot.vdi')
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, '', ''),
        (['VBoxManage'], 0, vbm_infos['usage'], ''),
        (['VBoxManage', 'list', 'systemproperties'], 0, vbm_infos['systemproperties'], ''),
        (['VBoxManage', 'createvm', '--name', 'foo', '--basefolder', tempdir.directory, '--ostype', 'Other', '--register'], 0, '', ''),
        (['VBoxManage', 'list', 'vms'], 0, '"foo" {%s}' % uid, ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), ''),
        (['VBoxManage', 'storagectl', 'foo', '--name', 'sata', '--add', 'sata'], 0, '', ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.storagectl(name='sata'), ''),
        (['VBoxManage', 'createhd', '--filename', boot_vdi, '--format', 'VDI', '--size', '102400'], 0, '', ''),
        (['VBoxManage', 'storageattach', 'foo', '--medium', boot_vdi, '--port', '0', '--storagectl', 'sata', '--type', 'hdd'], 0, '', ''),
        (['VBoxManage', 'startvm', 'foo'], 0, '', '')]
    ctrl(['./bin/ploy', 'start', 'foo'])
    assert popen_mock.expect == []
    assert caplog_messages(caplog) == [
        "Creating instance 'foo'",
        "Adding default 'sata' controller.",
        "Starting instance 'vb-instance:foo'",
        "Instance started"]


def test_start_with_dvd(ctrl, ployconf, popen_mock, tempdir, vbm_infos, caplog):
    import uuid
    uid = str(uuid.uuid4())
    ployconf.fill([
        '[vb-disk:boot]',
        'size = 102400',
        '[vb-instance:foo]',
        'storage = --type dvddrive --medium mfsbsd.iso'])
    vminfo = VMInfo()
    medium = os.path.join(ployconf.directory, 'mfsbsd.iso')
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, '', ''),
        (['VBoxManage'], 0, vbm_infos['usage'], ''),
        (['VBoxManage', 'list', 'systemproperties'], 0, vbm_infos['systemproperties'], ''),
        (['VBoxManage', 'createvm', '--name', 'foo', '--basefolder', tempdir.directory, '--ostype', 'Other', '--register'], 0, '', ''),
        (['VBoxManage', 'list', 'vms'], 0, '"foo" {%s}' % uid, ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.state('poweroff'), ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo(), ''),
        (['VBoxManage', 'storagectl', 'foo', '--name', 'sata', '--add', 'sata'], 0, '', ''),
        (['VBoxManage', 'showvminfo', '--machinereadable', 'foo'], 0, vminfo.storagectl(name='sata'), ''),
        (['VBoxManage', 'storageattach', 'foo', '--medium', medium, '--port', '0', '--storagectl', 'sata', '--type', 'dvddrive'], 0, '', ''),
        (['VBoxManage', 'startvm', 'foo'], 0, '', '')]
    ctrl(['./bin/ploy', 'start', 'foo'])
    assert popen_mock.expect == []
    assert caplog_messages(caplog) == [
        "Creating instance 'foo'",
        "Adding default 'sata' controller.",
        "Starting instance 'vb-instance:foo'",
        "Instance started"]


def test_status(ctrl, popen_mock, caplog):
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, '', '')]
    ctrl(['./bin/ploy', 'status', 'foo'])
    assert popen_mock.expect == []
    assert caplog_messages(caplog) == [
        "Instance 'foo' unavailable"]


def test_stop(ctrl, popen_mock, caplog):
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, '', '')]
    ctrl(['./bin/ploy', 'stop', 'foo'])
    assert popen_mock.expect == []
    assert caplog_messages(caplog) == [
        "Instance 'foo' unavailable"]


def test_terminate(ctrl, popen_mock, yesno_mock, caplog):
    popen_mock.expect = [
        (['VBoxManage', 'list', 'vms'], 0, '', '')]
    yesno_mock.expected = [
        ("Are you sure you want to terminate 'vb-instance:foo'?", True)]
    ctrl(['./bin/ploy', 'terminate', 'foo'])
    assert popen_mock.expect == []
    assert caplog_messages(caplog) == [
        "Instance 'foo' unavailable"]
