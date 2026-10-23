#!/usr/bin/python3
"""Headless local alert inbox. Acknowledgement never means a fault was repaired."""
import argparse
import json
from pathlib import Path
from alert_store import AlertStore, AlertUnavailable


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir',type=Path)
    sub=parser.add_subparsers(dest='command',required=True)
    listing=sub.add_parser('list');listing.add_argument('--limit',type=int,default=20)
    listing.add_argument('--attention',choices=['new','seen','acknowledged'])
    show=sub.add_parser('show');show.add_argument('alert_id')
    for name in ['ack','seen']:
        action=sub.add_parser(name);action.add_argument('alert_id');action.add_argument('--version',type=int,required=True)
    sub.add_parser('status')
    args=parser.parse_args()
    try:
        store=AlertStore(args.state_dir,read_only=args.command in ('list','show','status'))
        if args.command=='list':result={'alerts':store.list_alerts(args.limit,args.attention),'resolved':False}
        elif args.command=='show':result=store.get_alert(args.alert_id)
        elif args.command=='ack':result=store.acknowledge(args.alert_id,args.version);store.write_legacy()
        elif args.command=='seen':result=store.mark_seen(args.alert_id,args.version);store.write_legacy()
        else:result=store.legacy_snapshot()
    except (FileNotFoundError,AlertUnavailable):
        result={'available':False,'alerts':[],'note':'Alert collector has not created its inbox'}
    except (ValueError,OSError) as error:
        parser.exit(1,type(error).__name__+': '+str(error)+'\n')
    print(json.dumps(result,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
