from lazy import lazy
from mr.awsome.common import BaseMaster
from mr.awsome.config import BooleanMassager, PathMassager
from mr.awsome.plain import Instance as PlainInstance
import logging
import os
import subprocess
import sys
import time


log = logging.getLogger('mr.awsome.virtualbox')


class VirtualBoxError(Exception):
    pass


class Instance(PlainInstance):
    sectiongroupname = 'vb-instance'

    @lazy
    def _vmfolder(self):
        folder = self.config.get('basefolder')
        if folder is None:
            folder = self.master.master_config.get('basefolder')
        if folder is None:
            folder = self.vb.list.systemproperties().get('Default machine folder')
        if folder is None:
            raise VirtualBoxError("No basefolder configured for VM '%s'." % self.id)
        return os.path.join(folder, self.id)

    @lazy
    def vb(self):
        import vbox
        return vbox.pyVb.VirtualBox().cli.manage

    def _vminfo(self):
        info = self.vb.showvminfo(self.id)
        return dict(self.vb.cli.util.parseMachineReadableFmt(info))

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
                    name=self.id, basefolder=self._vmfolder, register=True)
            except subprocess.CalledProcessError as e:
                log.error("Failed to create VM '%s':\n%s" % (self.id, e))
                sys.exit(1)
            status = self._status()
        if status != 'stopped':
            log.info("Instance state: %s", status)
            log.info("Instance already started")
            return True
        try:
            kw = {}
            if config.get('headless', self._vmheadless):
                kw['type'] = 'headless'
            self.vb.startvm(self.id, **kw)
        except subprocess.CalledProcessError as e:
            log.error("Failed to start VM '%s':\n%s" % (self.id, e))
            return


class Master(BaseMaster):
    sectiongroupname = 'vb-master'
    section_info = {
        None: Instance,
        'vb-instance': Instance}


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
