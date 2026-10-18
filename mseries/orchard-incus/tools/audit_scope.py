"""Guest/destination boundary for the opt-in, mutating desktop audit."""
from pathlib import Path


class AuditScope:
    def __init__(self, names, output):
        self.names = names
        self.output = Path(output).resolve()

    def guest(self, name):
        if name not in self.names:
            raise RuntimeError('Audit rejected an instance outside its owned fixture names')

    def host_path(self, path):
        if not Path(path).resolve().is_relative_to(self.output):
            raise RuntimeError('Audit rejected a host path outside its output directory')

    def check(self, args):
        args = tuple(args)
        if not args:
            raise RuntimeError('Audit rejected an empty CLI operation')
        verb = args[0]
        if verb in ('list', 'info', 'version', 'monitor'):
            return
        if verb == 'query' and not any(x == '-X' or x.startswith('--request') or x.startswith('-X') for x in args[1:]):
            return
        if verb in ('image', 'network', 'storage', 'profile') and args[1] in ('list', 'show', 'info'):
            return
        if verb == 'config':
            if args[1] in ('show', 'get'):
                return
            if args[1] == 'set':
                self.guest(args[2]); return
            if args[1:3] in (('device', 'add'), ('device', 'remove')):
                self.guest(args[3])
                if 'disk' in args[4:]:
                    for arg in args[4:]:
                        if arg.startswith('source='):
                            self.host_path(arg.split('=', 1)[1])
                return
        if verb in ('start', 'stop', 'restart', 'pause', 'freeze', 'unfreeze', 'delete'):
            targets = [x for x in args[1:] if not x.startswith('-')]
            if len(targets) == 1:
                self.guest(targets[0]); return
        if verb in ('copy', 'rename') and len(args) == 3:
            self.guest(args[1]); self.guest(args[2]); return
        if verb == 'snapshot' and args[1] in ('create', 'restore', 'delete', 'list'):
            self.guest(args[2]); return
        if verb == 'exec':
            self.guest(args[1]); return
        if verb == 'export' and len(args) == 3:
            self.guest(args[1]); self.host_path(args[2]); return
        if verb == 'file' and args[1] in ('push', 'pull'):
            paths = [x for x in args[2:] if not x.startswith('-')]
            if len(paths) == 2:
                guest, host = (paths[1], paths[0]) if args[1] == 'push' else paths
                self.guest(guest.split('/', 1)[0]); self.host_path(host); return
        raise RuntimeError('Audit rejected an unrecognized or unscoped CLI operation')
