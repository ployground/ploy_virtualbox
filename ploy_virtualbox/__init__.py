from lazy import lazy
from ploy.common import BaseMaster
from ploy.config import BooleanMassager, PathMassager
from ploy.config import expand_path
from ploy.plain import Instance as PlainInstance
import logging
import os
import re
import subprocess
import shlex
import sys
import time


log = logging.getLogger('ploy_virtualbox')


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
            folder = self.vb.list_systemproperties().get('Default machine folder')
        if folder is None:
            raise VirtualBoxError("No basefolder configured for VM '%s'." % self.id)
        return folder

    @lazy
    def _vmfolder(self):
        return os.path.join(self._vmbasefolder, self.id)

    @lazy
    def vb(self):
        from ploy_virtualbox.vbox import VBoxManage
        return VBoxManage()

    def _vminfo(self, group=None, namekey=None):
        info = self.vb.showvminfo(self.id)
        if group is None:
            return info
        result = {}
        matcher = re.compile('%s(\D*)(\d+)' % group)
        for key, value in info.items():
            m = matcher.match(key)
            if m:
                name, index = m.groups()
                d = result.setdefault(index, {})
                d[name] = value
                if name == 'name':
                    result[value] = d
        if namekey:
            for key in list(result):
                if key != result[key][namekey]:
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
            vms = self.vb.list('vms')
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

    def _get_forwarding_info(self):
        result = {}
        for key, value in self._vminfo().items():
            if not key.startswith('Forwarding'):
                continue
            if 'ssh' not in value:
                continue
            names = ('name', 'proto', 'hostip', 'hostport', 'guestip', 'guestport')
            result.update(zip(names, value.split(',')))
            if not result['hostip']:
                result['hostip'] = "127.0.0.1"
        return result

    def get_host(self):
        try:
            return PlainInstance.get_host(self)
        except KeyError:
            pass
        return self._get_forwarding_info()['hostip']

    def get_port(self):
        return self._get_forwarding_info().get('hostport', 22)

    def status(self):
        vms = self.vb.list('vms')
        status = self._status(vms)
        if status == 'unavailable':
            log.info("Instance '%s' unavailable", self.id)
            return
        if status != 'running':
            log.info("Instance state: %s", status)
            return
        gp = self.vb.guestproperty('enumerate', self.id)
        for ifnum, ifinfo in self._vminfo(group='nic').items():
            ifindex = int(ifnum) - 1
            if ifinfo[''] in ('none', 'nat'):
                continue
            ip = gp.get('/VirtualBox/GuestInfo/Net/%s/V4/IP' % ifindex, {}).get('value')
            if not ip:
                continue
            log.info("IP for %s interface: %s" % (ifinfo[''], ip))
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
        self.vb.unregistervm(self.id, '--delete')
        log.info("Instance terminated")

    def _get_modifyvm_args(self, config, create):
        args = []
        for config_key, value in config.items():
            if not config_key.startswith('vm-'):
                continue
            key = config_key[3:]
            if not create and key.startswith(('natpf',)):
                continue
            if key.startswith('uartmode'):
                if value == 'disconnected':
                    pass
                elif value.startswith(('server ', 'client ', 'file ')):
                    value = value.split(None, 1)
                    args.extend(("--%s" % key, value[0], expand_path(value[1], config.get_path(config_key))))
                else:
                    args.extend(("--%s" % key, expand_path(value, config.get_path(config_key))))
            elif key.startswith('uart') and value != 'off':
                value = value.split()
                args.append("--%s" % key)
                args.extend(value)
            else:
                args.extend(("--%s" % key, value))
        return args

    def start(self, overrides=None):
        config = self.get_config(overrides)
        status = self._status()
        create = False
        if status == 'unavailable':
            create = True
            log.info("Creating instance '%s'", self.id)
            try:
                self.vb.createvm(
                    '--name', self.id, '--basefolder', self._vmbasefolder,
                    '--ostype', config.get('vm-ostype', 'Other'), '--register')
            except subprocess.CalledProcessError as e:
                log.error("Failed to create VM '%s':\n%s" % (self.id, e))
                sys.exit(1)
            status = self._status()
        if status != 'stopped':
            log.info("Instance state: %s", status)
            log.info("Instance already started")
            return True
        # modify vm
        args = self._get_modifyvm_args(config, create)
        if args:
            try:
                self.vb.modifyvm(self.id, *args)
            except subprocess.CalledProcessError as e:
                log.error("Failed to modify VM '%s':\n%s" % (self.id, e))
                sys.exit(1)
        # storagectl
        storagectls = self._vminfo(group='storagecontroller', namekey='name')
        for key, value in config.items():
            if not key.startswith('storagectl-'):
                continue
            name = key[11:]
            args = shlex.split(value)
            if name in storagectls:
                continue
            try:
                self.vb.storagectl(self.id, '--name', name, *args)
            except subprocess.CalledProcessError as e:
                log.error("Failed to create storage controller '%s' for VM '%s':\n%s" % (name, self.id, e))
                sys.exit(1)
        storagectls = self._vminfo(group='storagecontroller', namekey='name')
        # storageattach
        storages = list(filter(None, config.get('storage', '').splitlines()))
        if storages and not storagectls:
            log.info("Adding default 'sata' controller.")
            try:
                self.vb.storagectl(self.id, '--name', 'sata', '--add', 'sata')
            except subprocess.CalledProcessError as e:
                log.error("Failed to create default storage controller for VM '%s':\n%s" % (self.id, e))
                sys.exit(1)
            storagectls = self._vminfo(group='storagecontroller', namekey='name')
        for index, storage in enumerate(storages):
            args = shlex.split(storage)
            args_dict = {}
            for k, v in zip(*[iter(args)] * 2):
                args_dict[k[2:]] = v
            if 'medium' in args_dict:
                medium = args_dict['medium']
                if '.' in medium:
                    medium = expand_path(medium, config.get_path('storage'))
                elif medium.startswith('vb-disk:'):
                    medium = self.master.disks[medium[8:]].filename(self)
                args_dict['medium'] = medium
            if 'storagectl' not in args_dict:
                if len(storagectls) == 1:
                    args_dict['storagectl'] = list(storagectls.keys())[0]
                else:
                    log.error("You have to select the controller for storage '%s' on VM '%s'." % (index, self.id))
                    sys.exit(1)
            if 'type' not in args_dict:
                args_dict['type'] = 'hdd'
            if 'port' not in args_dict:
                args_dict['port'] = str(index)
            try:
                self.vb.storageattach(self.id, **args_dict)
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
        PathMassager(sectiongroupname, 'basefolder')])

    sectiongroupname = 'vb-instance'
    massagers.extend(get_instance_massagers(sectiongroupname))

    return massagers


def get_macro_cleaners(main_config):
    def clean_instance(macro):
        for key in macro.keys():
            if key in ('ip',):
                del macro[key]

    return {"vb-instance": clean_instance}


def get_masters(ctrl):
    masters = ctrl.config.get('vb-master', {'vb-master': {}})
    for master, master_config in masters.items():
        yield Master(ctrl, master, master_config)


plugin = dict(
    get_massagers=get_massagers,
    get_macro_cleaners=get_macro_cleaners,
    get_masters=get_masters)
