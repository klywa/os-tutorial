#!/usr/bin/env python3
"""Start or inspect this project's persistent local backend and Vite frontend."""
import argparse
import json
from pathlib import Path
import sys
import local_supervisor as supervisor

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--restart-backend',action='store_true')
    parser.add_argument('--build',action='store_true')
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--status',action='store_true')
    group.add_argument('--stop',action='store_true',help='Pause automatic restart and stop both services safely')
    args=parser.parse_args()
    try:
        if args.status:result=supervisor.status(args.root)
        elif args.stop:
            supervisor._bootstrap(args.root)
            result=supervisor.stop(args.root)
        else:result=supervisor.ensure(args.root,args.restart_backend,args.build)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except Exception as exc:
        print(str(exc),file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
