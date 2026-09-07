"""Serialize this command in CI. Uses pre-authenticated Databricks CLI; never logs credentials."""
import argparse
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime, timezone


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', choices=['dev', 'test', 'prod'], required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--as-of', required=True, help='UTC logical cutoff: YYYY-MM-DD HH:MM:SS')
    args = parser.parse_args()
    datetime.strptime(args.as_of, '%Y-%m-%d %H:%M:%S')
    env = dict(os.environ, BUNDLE_VAR_run_id=args.run_id, BUNDLE_VAR_as_of=args.as_of)
    root = Path(__file__).resolve().parents[1]
    for action in ('validate', 'deploy', 'run'):
        command = ['databricks', 'bundle', action, '-t', args.target]
        if action == 'run':
            command.append('refresh_gold')
        try:
            result = subprocess.run(command, cwd=root, env=env, check=False)
        except OSError as exc:
            print(json.dumps({'event': 'orchestration_error', 'action': action,
                              'pipeline_run_id': args.run_id, 'error_type': type(exc).__name__}), flush=True)
            raise SystemExit(127) from exc
        print(json.dumps({'event': 'bundle_' + action, 'target': args.target,
                          'pipeline_run_id': args.run_id, 'as_of': args.as_of,
                          'exit_code': result.returncode,
                          'logged_at': datetime.now(timezone.utc).isoformat()}), flush=True)
        if result.returncode:
            raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
