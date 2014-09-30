from lazy import lazy
from ploy.common import shjoin
import logging
import re
import subprocess


log = logging.getLogger('ploy_virtualbox.vbox')


def dequote(txt):
    quote = "\"'"
    out = txt.strip()
    if not out:
        return ""
    ch = out[0]
    if (ch in quote) and (ch == out[-1]):
        out = out[1:-1]
    return out


def iter_matches(exp, lines):
    for line in lines:
        m = exp.match(line)
        if m:
            yield m.groups()


def parse_list_result(sep, lines):
    result = dict()
    for line in lines:
        key, value = line.split(sep, 1)
        result[dequote(key)] = dequote(value)
    return result


class VBoxManage:
    def __init__(self, executable="VBoxManage", instance=None):
        self.executable = executable
        self.instance = instance

    list_vms_re = re.compile(r"^\s*(['\"])(.*?)\1\s+{(.*?)}\s*$")

    def createhd(self, *args, **kw):
        return self('createhd', *args, rc=0, **kw)

    def controlvm(self, name, cmd, *args, **kw):
        key = 'controlvm_%s' % cmd
        if hasattr(self, key):
            return getattr(self, key)(name, *args, **kw)
        return self('controlvm', name, cmd, *args, **kw)

    def controlvm_poweroff(self, name, *args, **kw):
        return self('controlvm', name, 'poweroff', *args, rc=0, **kw)

    guestproperty_re = re.compile('Name: (.*), value: (.*), timestamp: (.*), flags: (.*)')

    def guestproperty(self, name, *args, **kw):
        lines = self('guestproperty', name, *args, rc=0, err='', **kw)
        result = dict()
        matches = iter_matches(self.guestproperty_re, lines)
        for name, value, timestamp, flags in matches:
            flags = [x.strip() for x in flags.split(',')]
            result[name] = dict(value=value, timestamp=timestamp, flags=flags)
        return result

    def hostonlyif(self, cmd, *args, **kw):
        key = 'hostonlyif_%s' % cmd
        if hasattr(self, key):
            return getattr(self, key)(*args, **kw)
        return self('hostonlyif', cmd, *args, rc=0, **kw)

    def list(self, cmd, *args, **kw):
        key = 'list_%s' % cmd
        if hasattr(self, key):
            return getattr(self, key)(*args, **kw)
        return self('list', cmd, *args, **kw)

    def list_dhcpservers(self, *args, **kw):
        lines = self('list', 'dhcpservers', *args, rc=0, err='', **kw)
        block = []
        result = {}
        for line in lines:
            if not line:
                info = parse_list_result(':', block)
                result[info['NetworkName']] = info
                block = []
            else:
                block.append(line)
        return result

    def list_hostonlyifs(self, *args, **kw):
        lines = self('list', 'hostonlyifs', *args, rc=0, err='', **kw)
        block = []
        result = {}
        for line in lines:
            if not line:
                info = parse_list_result(':', block)
                result[info['Name']] = info
                block = []
            else:
                block.append(line)
        return result

    def list_systemproperties(self, *args, **kw):
        lines = self('list', 'systemproperties', *args, rc=0, err='', **kw)
        return parse_list_result(':', lines)

    def list_vms(self, *args, **kw):
        lines = self('list', 'vms', *args, rc=0, err='', **kw)
        return dict((x[1], x[2]) for x in iter_matches(self.list_vms_re, lines))

    def showvminfo(self, *args, **kw):
        lines = self('showvminfo', '--machinereadable', *args, rc=0, err='', **kw)
        return parse_list_result('=', lines)

    def unregistervm(self, name, *args, **kw):
        return self('unregistervm', name, *args, rc=0, **kw)

    @lazy
    def commands(self):
        lines = iter(x for x in self(rc=0, err='') if x.strip())
        for line in lines:
            if line.startswith(b'Commands:'):
                break
        result = set()
        count = 0
        for line in lines:
            if line[:4].strip():
                count = 0
            if not count:
                result.add(line[:28].strip().split(None, 1)[0].decode('ascii'))
            count += 1
        return sorted(result)

    def __getattr__(self, name):
        if name not in self.commands:
            raise AttributeError(name)
        return lambda *args, **kw: self(name, *args, rc=0, err='', **kw)

    def _local_call(self, cmd_args):
        log.debug(cmd_args)
        proc = subprocess.Popen(
            cmd_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _out, _err = proc.communicate()
        _rc = proc.returncode
        return _rc, _out, _err

    def _remote_call(self, cmd_args):
        cmd = shjoin(cmd_args)
        log.debug(cmd)
        chan = self.instance.conn.get_transport().open_session()
        rout = chan.makefile('rb', -1)
        rerr = chan.makefile_stderr('rb', -1)
        chan.exec_command(cmd)
        _out = rout.read()
        _err = rerr.read()
        _rc = chan.recv_exit_status()
        return _rc, _out, _err

    def __call__(self, *args, **kw):
        rc = kw.pop('rc', None)
        out = kw.pop('out', None)
        err = kw.pop('err', None)
        cmd_args = [self.executable]
        cmd_args.extend(args)
        for k, v in sorted(kw.items()):
            cmd_args.append("--%s" % k)
            cmd_args.append(v)
        if self.instance is None:
            _rc, _out, _err = self._local_call(cmd_args)
        else:
            _rc, _out, _err = self._remote_call(cmd_args)
        result = []
        if rc is None:
            result.append(_rc)
        else:
            try:
                if not any(x == _rc for x in rc):
                    raise subprocess.CalledProcessError(_rc, ' '.join(cmd_args), _err)
            except TypeError:
                pass
            if rc != _rc:
                raise subprocess.CalledProcessError(_rc, ' '.join(cmd_args), _err)
        if out is None:
            result.append(_out.splitlines())
        else:
            if out != _out:
                if _rc == 0:
                    log.error(_out)
                raise subprocess.CalledProcessError(_rc, ' '.join(cmd_args), _err)
        if err is None:
            result.append(_err.splitlines())
        else:
            if err != _err:
                if _rc == 0:
                    log.error(_err)
                raise subprocess.CalledProcessError(_rc, ' '.join(cmd_args), _err)
        if len(result) == 0:
            return
        elif len(result) == 1:
            return result[0]
        return tuple(result)
