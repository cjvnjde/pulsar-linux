import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys
from .protocol import plan
from .paths import history_dir
from .transport import Mouse,discover

def main(argv=None):
    parser=argparse.ArgumentParser(description='Native HATOR Pulsar 3 (379a:3910) configuration')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('detect',help='Identify mouse and required device access without opening it')
    sub.add_parser('status',help='Read live polling rate, active stage and lighting status')
    sub.add_parser('probe',help='Read descriptors and live status; never writes configuration')
    for verb in ('plan','apply'):
        p=sub.add_parser(verb,help='Preview packets' if verb=='plan' else 'Write an explicit profile to the mouse')
        p.add_argument('profile',type=Path)
        p.add_argument('--sections',default='parameters,dpi,colors,buttons,macros',help='Comma-separated groups to write')
        if verb=='apply':p.add_argument('--commit',action='store_true',help='Actually send settings (otherwise previews only)')
    args=parser.parse_args(argv)
    if args.command=='detect':
        info=discover();info['accessible']=all(os.access(info[k],os.R_OK|os.W_OK) for k in ('usb','status_hidraw') if info[k])
        print(json.dumps(info,indent=2));return 0
    if args.command in ('status','probe'):
        with Mouse() as mouse:
            result={'device':mouse.info}
            if args.command=='probe':result['report_descriptors']=mouse.descriptors()
            result['status']=mouse.status()
        print(json.dumps(result,indent=2));return 0
    config=json.loads(args.profile.read_text())
    sections=args.sections.split(',')
    if not all(sections):raise ValueError('Empty section name')
    packets=plan(config,sections)
    if args.command=='plan' or not args.commit:
        print(json.dumps({'writes_hardware':False,'packets':[p.as_dict() for p in packets]},indent=2));return 0
    # Validate every packet before opening the device; make a write journal first.
    journal_dir=history_dir();journal_dir.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    journal=journal_dir/(stamp+'.json')
    record={'profile':config,'sections':sections,'completed_packets':[],
            'warning':'This is a record of requested writes, not a backup read from the device.'}
    journal.write_text(json.dumps(record,indent=2)+'\n')
    try:
        with Mouse() as mouse:
            record['before_status']=mouse.status()
            journal.write_text(json.dumps(record,indent=2)+'\n')
            for packet in packets:
                mouse.send(packet);record['completed_packets'].append(packet.name)
                journal.write_text(json.dumps(record,indent=2)+'\n')
            record['after_status']=mouse.status()
        record['result']='USB transfers completed; status captured. Settings absent from status need functional verification.'
    except BaseException as error:
        record['error']=str(error);journal.write_text(json.dumps(record,indent=2)+'\n');raise
    journal.write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({'journal':str(journal),'status':record['after_status'],'result':record['result']},indent=2))
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except (OSError,ValueError,RuntimeError,KeyError) as e:
        print(f'Error: {e}',file=sys.stderr)
        if isinstance(e,PermissionError):print('Run `python -m pulsar3 detect` to identify device files requiring access.',file=sys.stderr)
        sys.exit(1)
