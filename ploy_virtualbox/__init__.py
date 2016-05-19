from __future__ import unicode_literals
from lazy import lazy
from ploy.common import BaseMaster, yesno
from ploy.config import BooleanMassager, PathMassager
from ploy.config import expand_path
from ploy.plain import Instance as PlainInstance
from ploy.proxy import ProxyInstance
try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse
import hashlib
import logging
import os
import re
import subprocess
import shlex
import sys
import time
import urllib

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

    @property
    def vb(self):
        return self.master.vb

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
        for retry in (True, False):
            try:
                status = self._vminfo()['VMState']
                break
            except subprocess.CalledProcessError as e:
                if retry:
                    time.sleep(0.5)
                else:
                    log.error("Couldn't get status of '%s':\n%s" % (self.config_id, e))
                    sys.exit(1)
        if status in ('running', 'stopping'):
            return 'running'
        elif status == 'poweroff':
            return 'stopped'
        elif status == 'saved':
            return 'saved'
        elif status == 'aborted':
            log.warn("Instance '%s' is in state '%s'." % (self.config_id, status))
            return 'aborted'
        raise VirtualBoxError("Don't know how to handle VM '%s' in state '%s'" % (self.config_id, status))

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

    def init_ssh_key(self, user=None):
        mi = getattr(self.master, 'instance', None)
        if mi is not None and 'proxyhost' not in self.config:
            self.config['proxyhost'] = self.master.id
        if mi is not None and 'proxycommand' not in self.config:
            self.config['proxycommand'] = self.proxycommand_with_instance(mi)
        return PlainInstance.init_ssh_key(self, user=user)

    def status(self):
        vms = self.vb.list('vms')
        try:
            status = self._status(vms)
        except VirtualBoxError as e:
            log.error(e)
            return
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
        if status not in ('stopped', 'saved', 'aborted'):
            log.info('Waiting for instance to stop')
            while status != 'stopped':
                status = self._status()
                sys.stdout.write('.')
                sys.stdout.flush()
                time.sleep(1)
            print
        for index, args_dict in enumerate(self._get_storages(self.config)):
            if 'medium' in args_dict:
                medium = args_dict['medium']
                if isinstance(medium, Disk):
                    if not medium.delete:
                        storagectls = self._vminfo(group='storagecontroller', namekey='name')
                        if 'storagectl' not in args_dict:
                            if len(storagectls) == 1:
                                args_dict['storagectl'] = list(storagectls.keys())[0]
                            else:
                                log.error("You have to select the controller for storage '%s' on VM '%s'." % (index, self.id))
                                sys.exit(1)
                        if 'port' not in args_dict:
                            args_dict['port'] = str(index)
                        args_dict['medium'] = 'none'
                        try:
                            self.vb.storageattach(self.id, **args_dict)
                        except subprocess.CalledProcessError as e:
                            log.error("Failed to deattach storage #%s from VM '%s':\n%s" % (index + 1, self.id, e))
                            sys.exit(1)
        log.info("Terminating instance '%s'", self.id)
        self.vb.unregistervm(self.id, '--delete')
        log.info("Instance terminated")

    def _get_modifyvm_args(self, config, create):
        args = []
        for config_key, value in config.items():
            if not config_key.startswith('vm-'):
                continue
            key = config_key[3:]
            if not create and key.startswith(('natpf', 'hostonlyadapter')):
                continue
            if key.startswith('hostonlyadapter'):
                hostonlyif = self.master.hostonlyifs[value]
                hostonlyif.ensure(self)
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

    def _start(self, config):
        try:
            kw = {}
            if config.get('headless', self._vmheadless):
                kw['type'] = 'headless'
            self.vb.startvm(self.id, **kw)
        except subprocess.CalledProcessError as e:
            log.error("Failed to start VM '%s':\n%s" % (self.id, e))
            sys.exit(1)

    def _get_storages(self, config):
        storages = list(filter(None, config.get('storage', '').splitlines()))
        result = []
        for storage in storages:
            args = shlex.split(storage)
            args_dict = {}
            for k, v in zip(*[iter(args)] * 2):
                args_dict[k[2:]] = v
            if 'medium' in args_dict:
                medium = args_dict['medium']
                medium_url = urlparse(medium)
                if medium_url.netloc:
                    medium = (medium_url, args_dict.pop('medium_sha1', None))
                elif '.' in medium:
                    medium = expand_path(medium, config.get_path('storage'))
                elif medium.startswith('vb-disk:'):
                    try:
                        medium = self.master.disks[medium[8:]]
                    except KeyError:
                        log.error("Couldn't find [vb-disk:%s] section referenced by [%s]." % (medium[8:], self.config_id))
                        sys.exit(1)
                args_dict['medium'] = medium
            if 'type' not in args_dict:
                args_dict['type'] = 'hdd'
            result.append(args_dict)
        return result

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
        if status not in ('stopped', 'saved', 'aborted'):
            log.info("Instance state: %s", status)
            log.info("Instance already started")
            return True
        if status == 'saved':
            self._start(config)
            return
        # modify vm
        args = self._get_modifyvm_args(config, create)
        if args:
            try:
                self.vb.modifyvm(self.id, *args)
            except subprocess.CalledProcessError as e:
                log.error("Failed to modify VM '%s':\n%s\n%s" % (self.id, e, e.output))
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
        storages = self._get_storages(config)
        if storages and not storagectls:
            log.info("Adding default 'sata' controller.")
            try:
                self.vb.storagectl(self.id, '--name', 'sata', '--add', 'sata')
            except subprocess.CalledProcessError as e:
                log.error("Failed to create default storage controller for VM '%s':\n%s" % (self.id, e))
                sys.exit(1)
            storagectls = self._vminfo(group='storagecontroller', namekey='name')
        for index, args_dict in enumerate(storages):
            if 'medium' in args_dict:
                medium = args_dict['medium']
                if isinstance(medium, tuple):
                    medium = self.download_remote(*medium)
                elif isinstance(medium, Disk):
                    medium = medium.filename(self)
                args_dict['medium'] = medium
            if 'storagectl' not in args_dict:
                if len(storagectls) == 1:
                    args_dict['storagectl'] = list(storagectls.keys())[0]
                else:
                    log.error("You have to select the controller for storage '%s' on VM '%s'." % (index, self.id))
                    sys.exit(1)
            if 'port' not in args_dict:
                args_dict['port'] = str(index)
            try:
                self.vb.storageattach(self.id, **args_dict)
            except subprocess.CalledProcessError as e:
                log.error("Failed to attach storage #%s to VM '%s':\n%s" % (index + 1, self.id, e))
                sys.exit(1)
        log.info("Starting instance '%s'" % self.config_id)
        self._start(config)
        log.info("Instance started")

    def download_remote(self, url, sha_checksum=None):

        def check(path, sha):
            d = hashlib.sha1()
            with open(path, 'rb') as f:
                while 1:
                    buf = f.read(1024 * 1024)
                    if not len(buf):
                        break
                    d.update(buf)
            return d.hexdigest() == sha

        download_dir = os.path.expanduser(self.master.main_config.get('global', dict()).get(
            'download_dir', '~/.ploy/downloads'))

        if not os.path.exists(download_dir):
            os.makedirs(download_dir, mode=0o750)

        path, filename = os.path.split(url.path)
        local_path = os.path.join(download_dir, filename)

        if sha_checksum is None:
            if not yesno('No checksum provided! Are you sure you want to boot from an unverified image?'):
                sys.exit(1)

        if os.path.exists(local_path):
            if sha_checksum is None or check(local_path, sha_checksum):
                return local_path
            else:
                log.error('Checksum mismatch for %s!' % local_path)
                sys.exit(1)

        log.info("Downloading remote disk image from %s to %s" % (url.geturl(), local_path))
        urllib.urlretrieve(url.geturl(), local_path)
        log.info('Downloaded successfully to %s' % local_path)
        if sha_checksum is not None and not check(local_path, sha_checksum):
            log.error('Checksum mismatch!')
            sys.exit(1)

        return local_path


class DHCPServer(object):
    def __init__(self, name, config):
        self.name = name
        self.config = config

    def ensure(self, instance):
        dhcpservers = instance.vb.list('dhcpservers')
        name = "HostInterfaceNetworking-%s" % self.name
        kw = {}
        for key in ('ip', 'netmask', 'lowerip', 'upperip'):
            if key not in self.config:
                log.error("The '%s' option is required for dhcpserver '%s'." % (key, self.name))
                sys.exit(1)
            kw[key] = self.config[key]
        if name not in dhcpservers:
            try:
                instance.vb.dhcpserver('add', '--enable', netname=name, **kw)
            except subprocess.CalledProcessError as e:
                log.error("Failed to add dhcpserver '%s':\n%s" % (self.name, e))
                sys.exit(1)
            log.info("Added dhcpserver '%s'." % self.name)
        dhcpserver = instance.vb.list('dhcpservers')[name]
        matches = True
        if 'ip' in self.config:
            if dhcpserver['IP'] != self.config['ip']:
                log.error("The host only interface '%s' has an IP '%s' that doesn't match the config '%s'." % (
                    self.name, dhcpserver['IP'], self.config['ip']))
                matches = False
        if 'netmask' in self.config:
            if dhcpserver['NetworkMask'] != self.config['netmask']:
                log.error("The host only interface '%s' has an netmask '%s' that doesn't match the config '%s'." % (
                    self.name, dhcpserver['NetworkMask'], self.config['netmask']))
                matches = False
        if 'lower-ip' in self.config:
            if dhcpserver['lowerIPAddress'] != self.config['lower-ip']:
                log.error("The host only interface '%s' has a lower IP '%s' that doesn't match the config '%s'." % (
                    self.name, dhcpserver['lowerIPAddress'], self.config['lower-ip']))
                matches = False
        if 'upper-ip' in self.config:
            if dhcpserver['upperIPAddress'] != self.config['upper-ip']:
                log.error("The host only interface '%s' has a upper IP '%s' that doesn't match the config '%s'." % (
                    self.name, dhcpserver['upperIPAddress'], self.config['upper-ip']))
                matches = False
        if not matches:
            if not yesno("Should the dhcpserver '%s' be modified to match the config?" % self.name):
                sys.exit(1)
            try:
                instance.vb.dhcpserver('modify', '--enable', netname=name, **kw)
            except subprocess.CalledProcessError as e:
                log.error("Failed to modify dhcpserver '%s':\n%s" % (self.name, e))
                sys.exit(1)


class Disk(object):
    def __init__(self, name, config):
        self.name = name
        self.config = config

    def filename(self, instance):
        filename = self.config.get('filename')
        if filename is None:
            filename = self.name
        ext = ".%s" % self.format.lower()
        if not filename.endswith(ext):
            filename = filename + ext
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
    def delete(self):
        return self.config.get('delete', True)

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


class HostOnlyIF(object):
    def __init__(self, name, config):
        self.name = name
        self.config = config

    def ensure(self, instance):
        hostonlyifs = instance.vb.list('hostonlyifs')
        created = False
        if self.name not in hostonlyifs:
            newnames = set("vboxnet%s" % x for x in range(len(hostonlyifs) + 1))
            newnames = newnames - set(hostonlyifs)
            nextname = min(newnames)
            if nextname != self.name:
                log.error(
                    "The host only interface '%s' doesn't exist. "
                    "The next one to be created would be '%s'. "
                    "Since this doesn't match, we abort. "
                    "Please fix the config or handle the creation manually." % (
                        self.name, nextname))
                sys.exit(1)
            try:
                instance.vb.hostonlyif('create')
                created = True
            except subprocess.CalledProcessError as e:
                log.error("Failed to create host only interface '%s':\n%s" % (self.name, e))
                sys.exit(1)
            log.info("Created host only interface '%s'." % self.name)
        hostonlyif = instance.vb.list('hostonlyifs')[self.name]
        if created:
            kw = {}
            if 'ip' in self.config:
                kw['ip'] = self.config['ip']
            if kw:
                try:
                    instance.vb.hostonlyif('ipconfig', self.name, **kw)
                except subprocess.CalledProcessError as e:
                    log.error("Failed to configure host only interface '%s':\n%s" % (self.name, e))
                    sys.exit(1)
        else:
            if 'ip' in self.config:
                if hostonlyif['IPAddress'] != self.config['ip']:
                    log.error("The host only interface '%s' has an IP '%s' that doesn't match the config '%s'." % (
                        self.name, hostonlyif['IPAddress'], self.config['ip']))
                    sys.exit(1)
        try:
            dhcpserver = instance.master.dhcpservers[self.name]
        except KeyError:
            return
        dhcpserver.ensure(instance)


class InfoBase(object):
    def __init__(self, master):
        self.master = master
        self.config = self.master.main_config.get(self.sectiongroupname, {})
        self._cache = {}

    def __getitem__(self, key):
        if key not in self._cache:
            self._cache[key] = self.klass(key, self.config[key])
        return self._cache[key]


class DHCPServers(InfoBase):
    sectiongroupname = 'vb-dhcpserver'
    klass = DHCPServer


class Disks(InfoBase):
    sectiongroupname = 'vb-disk'
    klass = Disk


class HostOnlyIFs(InfoBase):
    sectiongroupname = 'vb-hostonlyif'
    klass = HostOnlyIF


class Master(BaseMaster):
    sectiongroupname = 'vb-instance'
    section_info = {
        None: Instance,
        'vb-instance': Instance}

    def __init__(self, *args, **kwargs):
        BaseMaster.__init__(self, *args, **kwargs)
        if 'instance' in self.master_config:
            self.instance = ProxyInstance(self, self.id, self.master_config, self.master_config['instance'])
            self.instance.sectiongroupname = 'vb-master'
            self.instances[self.id] = self.instance

    @lazy
    def dhcpservers(self):
        return DHCPServers(self)

    @lazy
    def disks(self):
        return Disks(self)

    @lazy
    def hostonlyifs(self):
        return HostOnlyIFs(self)

    @lazy
    def vb(self):
        from ploy_virtualbox.vbox import VBoxManage
        instance = getattr(self, 'instance', None)
        return VBoxManage(instance=instance)


def get_instance_massagers(sectiongroupname='instance'):
    return [
        PathMassager(sectiongroupname, 'basefolder'),
        BooleanMassager(sectiongroupname, 'headless'),
        BooleanMassager(sectiongroupname, 'use-acpi-powerbutton'),
        BooleanMassager(sectiongroupname, 'no-terminate')]


def get_massagers():
    massagers = []

    sectiongroupname = 'vb-disk'
    massagers.extend([
        BooleanMassager(sectiongroupname, 'delete')])

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
    masters = ctrl.config.get('vb-master', {'virtualbox': {}})
    for master, master_config in masters.items():
        yield Master(ctrl, master, master_config)


plugin = dict(
    get_massagers=get_massagers,
    get_macro_cleaners=get_macro_cleaners,
    get_masters=get_masters)
