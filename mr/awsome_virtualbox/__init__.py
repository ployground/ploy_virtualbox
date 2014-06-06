from lazy import lazy
from mr.awsome.common import BaseMaster
from mr.awsome.config import BooleanMassager, PathMassager
from mr.awsome.config import expand_path
from mr.awsome.plain import Instance as PlainInstance
import logging
import os
import re
import subprocess
import shlex
import sys
import time


log = logging.getLogger('mr.awsome.virtualbox')


class VirtualBoxError(Exception):
    pass


class Instance(PlainInstance):
    sectiongroupname = 'vb-instance'

    @lazy
    def _vmbasefolder(self):
        folder = self.config.get('basefolder')
        if folder is None:
            folder = self.master.master_config.get('basefolder')
        if folder is None:
            folder = self.vb.list.systemproperties().get('Default machine folder')
        if folder is None:
            raise VirtualBoxError("No basefolder configured for VM '%s'." % self.id)
        return folder

    @lazy
    def _vmfolder(self):
        return os.path.join(self._vmbasefolder, self.id)

    @lazy
    def vb(self):
        import vbox
        return vbox.pyVb.VirtualBox().cli.manage

    def _vminfo(self, group=None):
        info = self.vb.showvminfo(self.id)
        info = dict(self.vb.cli.util.parseMachineReadableFmt(info))
        if group is None:
            return info
        result = {}
        matcher = re.compile('%s(\D+)(\d+)' % group)
        for key, value in info.items():
            m = matcher.match(key)
            if m:
                name, index = m.groups()
                d = result.setdefault(index, {})
                d[name] = value
                if name == 'name':
                    result[value] = d
        for key in list(result):
            if key != result[key]['name']:
                del result[key]
        return result

    @property
    def _vmacpi(self):
        acpi = self.config.get('use-acpi-powerbutton')
        if acpi is None:
            acpi = self.master.master_config.get('use-acpi-powerbutton')
        if acpi is None:
            acpi = self._vminfo().get('acpi', '').lower() == 'on'
        return acpi

    @property
    def _vmheadless(self):
        acpi = self.config.get('headless')
        if acpi is None:
            acpi = self.master.master_config.get('headless', False)
        return acpi

    def _status(self, vms=None):
        if vms is None:
            vms = self.vb.list.vms()
        if self.id not in vms:
            return 'unavailable'
        status = self._vminfo()['VMState']
        if status == 'running':
            return 'running'
        elif status == 'poweroff':
            return 'stopped'
        raise VirtualBoxError("Don't know how to handle VM '%s' in state '%s'" % (self.id, status))

    def get_massagers(self):
        return get_instance_massagers()

    def get_host(self):
        raise NotImplementedError

    def status(self):
        vms = self.vb.list.vms()
        status = self._status(vms)
        if status == 'unavailable':
            log.info("Instance '%s' unavailable", self.id)
            return
        if status != 'running':
            log.info("Instance state: %s", status)
            return
        log.info("Instance running.")

    def stop(self):
        status = self._status()
        if status == 'unavailable':
            log.info("Instance '%s' unavailable", self.id)
            return
        if status != 'running':
            log.info("Instance state: %s", status)
            log.info("Instance not stopped")
            return
        log.info("Stopping instance '%s'", self.id)
        if self._vmacpi:
            log.info('Trying to stop instance with ACPI:')
            self.vb.controlvm(self.id, 'acpipowerbutton')
            count = 60
            while count > 0:
                status = self._status()
                sys.stdout.write('%3d\r' % count)
                sys.stdout.flush()
                time.sleep(1)
                count -= 1
                if status == 'stopped':
                    print
                    log.info("Instance stopped")
                    return
        print
        log.info("Stopping instance by sending 'poweroff'.")
        self.vb.controlvm(self.id, 'poweroff')
        log.info("Instance stopped")

    def terminate(self):
        status = self._status()
        if self.config.get('no-terminate', False):
            log.error("Instance '%s' is configured not to be terminated.", self.id)
            return
        if status == 'unavailable':
            log.info("Instance '%s' unavailable", self.id)
            return
        if status == 'running':
            log.info("Stopping instance '%s'", self.id)
            self.vb.controlvm(self.id, 'poweroff')
        if status != 'stopped':
            log.info('Waiting for instance to stop')
            while status != 'stopped':
                status = self._status()
                sys.stdout.write('.')
                sys.stdout.flush()
                time.sleep(1)
            print
        log.info("Terminating instance '%s'", self.id)
        self.vb.unregistervm(self.id, delete=True)
        log.info("Instance terminated")

    def start(self, overrides=None):
        config = self.get_config(overrides)
        status = self._status()
        if status == 'unavailable':
            log.info("Creating instance '%s'", self.id)
            try:
                self.vb.createvm(
                    name=self.id, basefolder=self._vmbasefolder,
                    ostype=config.get('vm-ostype'), register=True)
            except subprocess.CalledProcessError as e:
                log.error("Failed to create VM '%s':\n%s" % (self.id, e))
                sys.exit(1)
            status = self._status()
        if status != 'stopped':
            log.info("Instance state: %s", status)
            log.info("Instance already started")
            return True
        # modify vm
        args = []
        for key, value in config.items():
            if not key.startswith('vm-'):
                continue
            args.extend(("--%s" % key[3:], value))
        if args:
            try:
                self.vb.modifyvm(self.id, *args)
            except subprocess.CalledProcessError as e:
                log.error("Failed to modify VM '%s':\n%s" % (self.id, e))
                sys.exit(1)
        # storagectl
        storagectls = self._vminfo(group='storagecontroller')
        for key, value in config.items():
            if not key.startswith('storagectl-'):
                continue
            name = key[11:]
            args = shlex.split(value)
            args_dict = {}
            for k, v in zip(*[iter(args)] * 2):
                args_dict[k[2:]] = v
            if name in storagectls:
                continue
            try:
                self.vb.storagectl(self.id, name, **args_dict)
            except subprocess.CalledProcessError as e:
                log.error("Failed to create storage controller '%s' for VM '%s':\n%s" % (name, self.id, e))
                sys.exit(1)
        storagectls = self._vminfo(group='storagecontroller')
        # storageattach
        storages = filter(None, config.get('storage', '').split('\n'))
        if storages and not storagectls:
            log.info("Adding default 'sata' controller.")
            try:
                self.vb.storagectl(self.id, 'sata', add='sata')
            except subprocess.CalledProcessError as e:
                log.error("Failed to create default storage controller for VM '%s':\n%s" % (self.id, e))
                sys.exit(1)
            storagectls = self._vminfo(group='storagecontroller')
        storage_path_massager = PathMassager(config.sectiongroupname, 'storage')
        storage_path = storage_path_massager.path(config, self.id)
        for index, storage in enumerate(storages):
            args = shlex.split(storage)
            args_dict = {}
            for k, v in zip(*[iter(args)] * 2):
                args_dict[k[2:]] = v
            if 'medium' in args_dict:
                medium = args_dict['medium']
                if '.' in medium:
                    medium = expand_path(medium, storage_path)
                elif medium.startswith('vb-disk:'):
                    medium = self.master.disks[medium[8:]].filename(self)
                args_dict['medium'] = medium
            if 'storagectl' not in args_dict:
                if len(storagectls) == 1:
                    storagectl = storagectls.keys()[0]
                else:
                    log.error("You have to select the controller for storage '%s' on VM '%s'." % (index, self.id))
                    sys.exit(1)
            else:
                storagectl = args_dict['storagectl']
                del args_dict['storagectl']
            if 'type' not in args_dict:
                args_dict['type'] = 'hdd'
            if 'port' not in args_dict:
                args_dict['port'] = str(index)
            try:
                self.vb.storageattach(self.id, storagectl, **args_dict)
            except subprocess.CalledProcessError as e:
                log.error("Failed to attach storage #%s to VM '%s':\n%s" % (index + 1, self.id, e))
                sys.exit(1)
        try:
            kw = {}
            if config.get('headless', self._vmheadless):
                kw['type'] = 'headless'
            self.vb.startvm(self.id, **kw)
        except subprocess.CalledProcessError as e:
            log.error("Failed to start VM '%s':\n%s" % (self.id, e))
            sys.exit(1)


class Disk(object):
    def __init__(self, name, config):
        self.name = name
        self.config = config

    def filename(self, instance):
        filename = self.config.get('filename')
        if filename is None:
            filename = "%s.%s" % (self.name, self.format.lower())
        filename = expand_path(filename, instance._vmfolder)
        if not os.path.exists(filename):
            kw = {}
            if self.size:
                kw['size'] = self.size
            if self.variant:
                kw['variant'] = self.variant
            try:
                instance.vb.createhd(filename=filename, format=self.format, **kw)
            except subprocess.CalledProcessError as e:
                log.error("Failed to create disk '%s' at '%s':\n%s" % (self.name, filename, e))
                sys.exit(1)
        return filename

    @property
    def format(self):
        return self.config.get('format', 'VDI')

    @property
    def size(self):
        if 'size' not in self.config:
            log.error("You have to provide a size for vb-disk '%s'." % self.name)
            sys.exit(1)
        return self.config['size']

    @property
    def variant(self):
        return self.config.get('variant')


class Disks(object):
    def __init__(self, master):
        self.master = master
        self.config = self.master.main_config.get('vb-disk', {})
        self._cache = {}

    def __getitem__(self, key):
        if key not in self._cache:
            self._cache[key] = Disk(key, self.config[key])
        return self._cache[key]


class Master(BaseMaster):
    sectiongroupname = 'vb-master'
    section_info = {
        None: Instance,
        'vb-instance': Instance}

    @lazy
    def disks(self):
        return Disks(self)


def get_instance_massagers(sectiongroupname='instance'):
    return [
        PathMassager(sectiongroupname, 'basefolder'),
        BooleanMassager(sectiongroupname, 'headless'),
        BooleanMassager(sectiongroupname, 'use-acpi-powerbutton'),
        BooleanMassager(sectiongroupname, 'no-terminate')]


def get_massagers():
    massagers = []

    sectiongroupname = 'vb-master'
    massagers.extend([
        BooleanMassager(sectiongroupname, 'headless'),
        BooleanMassager(sectiongroupname, 'use-acpi-powerbutton'),
        PathMassager(sectiongroupname, 'basefolder'),
        PathMassager(sectiongroupname, 'vboxapi')])

    sectiongroupname = 'vb-instance'
    massagers.extend(get_instance_massagers(sectiongroupname))

    return massagers


def get_macro_cleaners(main_config):
    def clean_instance(macro):
        for key in macro.keys():
            if key in ('ip',):
                del macro[key]

    return {"vb-instance": clean_instance}


def get_masters(aws):
    masters = aws.config.get('vb-master', {})
    for master, master_config in masters.iteritems():
        yield Master(aws, master, master_config)


plugin = dict(
    get_massagers=get_massagers,
    get_macro_cleaners=get_macro_cleaners,
    get_masters=get_masters)
