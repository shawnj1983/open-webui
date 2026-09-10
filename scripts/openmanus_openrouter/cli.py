#!/usr/bin/env python3
"""CLI: wire OpenManus to OpenRouter with rotating API keys."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

if __name__ == '__main__' and (__package__ is None or __package__ == ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from openmanus_openrouter.keys import (
        DEFAULT_OPENROUTER_BASE,
        KeyRotator,
        resolve_keys,
        write_openmanus_config,
    )
else:
    from .keys import (
        DEFAULT_OPENROUTER_BASE,
        KeyRotator,
        resolve_keys,
        write_openmanus_config,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            'Run / configure OpenManus against OpenRouter using a pool of API keys '
            '(supports 12+ keys via env or a keys file). Never pass keys on the CLI.'
        )
    )
    sub = parser.add_subparsers(dest='command', required=True)

    status = sub.add_parser('status', help='Show how many OpenRouter keys are loaded')
    status.add_argument('--keys-file', help='Optional keys file (one key per line)')

    write = sub.add_parser('write-config', help='Write OpenManus config.toml for OpenRouter')
    write.add_argument('--keys-file', help='Optional keys file (one key per line)')
    write.add_argument(
        '--model',
        default=os.getenv('OPENROUTER_MODEL', 'openrouter/auto'),
        help='OpenRouter model id (default: OPENROUTER_MODEL or openrouter/auto)',
    )
    write.add_argument(
        '--base-url',
        default=os.getenv('OPENROUTER_BASE_URL', DEFAULT_OPENROUTER_BASE),
        help='OpenRouter OpenAI-compatible base URL',
    )
    write.add_argument(
        '--output',
        default='config/config.toml',
        help='Output path for OpenManus config (default: config/config.toml)',
    )
    write.add_argument(
        '--key-index',
        type=int,
        default=0,
        help='Which loaded key to embed (0-based). Prefer rotation via run.',
    )

    run = sub.add_parser('run', help='Write config with next rotated key and launch OpenManus')
    run.add_argument('--keys-file', help='Optional keys file (one key per line)')
    run.add_argument(
        '--model',
        default=os.getenv('OPENROUTER_MODEL', 'openrouter/auto'),
        help='OpenRouter model id',
    )
    run.add_argument(
        '--base-url',
        default=os.getenv('OPENROUTER_BASE_URL', DEFAULT_OPENROUTER_BASE),
        help='OpenRouter base URL',
    )
    run.add_argument(
        '--openmanus-dir',
        default=os.getenv('OPENMANUS_DIR', str(Path.home() / 'OpenManus')),
        help='Path to cloned OpenManus repo (default: ~/OpenManus or $OPENMANUS_DIR)',
    )
    run.add_argument(
        '--prompt',
        default=None,
        help='Optional one-shot prompt piped to OpenManus stdin',
    )
    run.add_argument(
        '--python',
        default=None,
        help='Python executable inside OpenManus venv (auto-detected if omitted)',
    )

    example = sub.add_parser('keys-example', help='Print a safe keys-file template')
    example.add_argument(
        '--count',
        type=int,
        default=12,
        help='How many key placeholder lines to print (default: 12)',
    )

    return parser


def cmd_status(args: argparse.Namespace) -> int:
    keys = resolve_keys(args.keys_file)
    print(f'Loaded OpenRouter keys: {len(keys)}')
    if not keys:
        print('Set OPENROUTER_API_KEYS, OPENROUTER_API_KEY_1..N, or --keys-file')
        return 1
    for index, key in enumerate(keys, start=1):
        masked = key[:6] + '…' + key[-4:] if len(key) > 12 else '***'
        print(f'  {index:02d}. {masked}')
    return 0


def cmd_write_config(args: argparse.Namespace) -> int:
    keys = resolve_keys(args.keys_file)
    if not keys:
        print('Error: no OpenRouter keys loaded', file=sys.stderr)
        return 1
    if args.key_index < 0 or args.key_index >= len(keys):
        print(f'Error: --key-index out of range (0..{len(keys) - 1})', file=sys.stderr)
        return 2

    path = write_openmanus_config(
        args.output,
        model=args.model,
        api_key=keys[args.key_index],
        base_url=args.base_url,
    )
    print(f'Wrote {path} using key #{args.key_index + 1}/{len(keys)} (mode={args.model})')
    return 0


def _detect_python(openmanus_dir: Path, override: str | None) -> str:
    if override:
        return override
    candidates = [
        openmanus_dir / '.venv' / 'bin' / 'python',
        openmanus_dir / 'venv' / 'bin' / 'python',
        openmanus_dir / '.venv' / 'Scripts' / 'python.exe',
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable


def cmd_run(args: argparse.Namespace) -> int:
    keys = resolve_keys(args.keys_file)
    if not keys:
        print('Error: no OpenRouter keys loaded', file=sys.stderr)
        return 1

    openmanus_dir = Path(args.openmanus_dir).expanduser().resolve()
    if not openmanus_dir.exists():
        print(
            f'Error: OpenManus dir not found: {openmanus_dir}\n'
            'Clone it first:\n'
            '  git clone https://github.com/FoundationAgents/OpenManus.git ~/OpenManus',
            file=sys.stderr,
        )
        return 1

    rotator = KeyRotator(keys)
    api_key = rotator.next_key()
    config_path = openmanus_dir / 'config' / 'config.toml'
    write_openmanus_config(
        config_path,
        model=args.model,
        api_key=api_key,
        base_url=args.base_url,
    )
    print(
        f'Using OpenRouter key 1 of {rotator.count} (rotated); wrote {config_path}',
        file=sys.stderr,
    )

    python_bin = _detect_python(openmanus_dir, args.python)
    main_py = openmanus_dir / 'main.py'
    if not main_py.exists():
        print(f'Error: missing {main_py}', file=sys.stderr)
        return 1

    env = os.environ.copy()
    env['OPENAI_API_KEY'] = api_key
    env['OPENROUTER_API_KEY'] = api_key
    cmd = [python_bin, str(main_py)]
    print(f'Launching: {" ".join(cmd)}', file=sys.stderr)

    if args.prompt:
        proc = subprocess.run(
            cmd,
            cwd=str(openmanus_dir),
            env=env,
            input=args.prompt + '\n',
            text=True,
            check=False,
        )
        return proc.returncode

    proc = subprocess.run(cmd, cwd=str(openmanus_dir), env=env, check=False)
    return proc.returncode


def cmd_keys_example(args: argparse.Namespace) -> int:
    print('# ~/.config/openrouter/keys.txt')
    print('# One OpenRouter key per line. Do not commit this file.')
    for i in range(1, max(1, args.count) + 1):
        print(f'# sk-or-v1-your-key-{i:02d}-here')
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == 'status':
        return cmd_status(args)
    if args.command == 'write-config':
        return cmd_write_config(args)
    if args.command == 'run':
        return cmd_run(args)
    if args.command == 'keys-example':
        return cmd_keys_example(args)
    parser.error(f'Unknown command: {args.command}')
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
