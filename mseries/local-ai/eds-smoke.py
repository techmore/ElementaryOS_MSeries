#!/usr/bin/python3
"""Verify Tasks/Calendar adapters with owned synthetic records, then remove them."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import uuid
from datetime import datetime, timedelta, timezone


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    import gi
    gi.require_version('EDataServer', '1.2')
    gi.require_version('ECal', '2.0')
    gi.require_version('ICalGLib', '3.0')
    from gi.repository import EDataServer, ECal, ICalGLib
    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here))
    spec = importlib.util.spec_from_file_location('os_mcp_smoke', here / 'os-mcp.py')
    adapter = importlib.util.module_from_spec(spec); spec.loader.exec_module(adapter)
    registry = EDataServer.SourceRegistry.new_sync(None)
    created, receipt = [], {}
    cases = [(EDataServer.SOURCE_EXTENSION_CALENDAR, ECal.ClientSourceType.EVENTS,
              'VEVENT', adapter.read_calendar, 'events'),
             (EDataServer.SOURCE_EXTENSION_TASK_LIST, ECal.ClientSourceType.TASKS,
              'VTODO', adapter.read_tasks, 'tasks')]
    try:
        for extension, kind, component, reader, key in cases:
            uid = 'mseries-eval-' + str(uuid.uuid4())
            source = EDataServer.Source.new_with_uid(uid, None)
            source.set_display_name('MSeries Synthetic Adapter Test')
            source.set_parent('local-stub')
            source.get_extension(extension).set_backend_name('local')
            registry.commit_source_sync(source, None); created.append(uid)
            client = ECal.Client.connect_sync(registry.ref_source(uid), kind, 5, None)
            start = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime('%Y%m%dT%H%M%SZ')
            end = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime('%Y%m%dT%H%M%SZ')
            body = 'DTSTART:' + start + '\nDTEND:' + end if component == 'VEVENT' else 'DUE:' + end
            title = 'MSeries synthetic ' + uid
            text = f'BEGIN:{component}\nUID:{uid}\nSUMMARY:{title}\n{body}\nEND:{component}\n'
            client.create_object_sync(ICalGLib.Component.new_from_string(text), ECal.OperationFlags.NONE, None)
            result = reader()
            # Neither private records nor source names enter this receipt/log.
            matched = sum(row['title'] == title for row in result[key]) == 1
            receipt[component] = {'synthetic_component_read': matched,
                                  'error_count': len(result['errors']), 'private_contents_published': False}
    finally:
        cleanup_errors = 0
        for uid in created:
            try:
                registry.ref_source(uid).remove_sync(None)
            except Exception:
                cleanup_errors += 1
        receipt['cleanup'] = {'owned_sources_removed': len(created) - cleanup_errors,
                              'errors': cleanup_errors}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2) + '\n')
    if cleanup_errors or not all(receipt.get(k, {}).get('synthetic_component_read') for k in ['VEVENT', 'VTODO']):
        raise SystemExit('Synthetic adapter verification or cleanup failed; inspect the bounded receipt.')
    print('Tasks and Calendar synthetic adapter checks passed; owned sources removed.')


if __name__ == '__main__':
    main()
