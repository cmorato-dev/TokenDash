"""Read Claude Code's experimental structured /usage through its own client.

Only control requests are sent: never a user message or a model prompt.
Prints a strict subset of numeric quota data, never raw client output.

This module is the single implementation of the protocol; ``claude_client`` loads it.
"""
import argparse
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path

WINDOWS = ('five_hour', 'seven_day')


def find_executable():
    """Locate the official client: PATH, the native install, or the VS Code extension."""
    installed = shutil.which('claude')
    if installed and (os.name != 'nt' or installed.lower().endswith('.exe')):
        return Path(installed)
    candidates = [Path.home() / '.local/bin/claude.exe']
    candidates += list((Path.home() / '.vscode/extensions').glob(
        'anthropic.claude-code-*/resources/native-binary/claude.exe'))
    candidates = [p for p in candidates if p.is_file()]
    if candidates:
        return max(candidates, key=lambda p: p.stat().st_mtime)
    # Native install on Linux/macOS: ~/.local/bin/claude points into the versions folder.
    native = Path.home() / '.local/bin/claude'
    if native.is_file():
        return native
    versions = Path.home() / '.local/share/claude/versions'
    if versions.is_dir():
        installed = [p for p in versions.glob('*') if p.is_file()]
        if installed:
            return max(installed, key=lambda p: p.stat().st_mtime)
    return None


def probe(executable, timeout=40, env=None):
    """Ask the client for its usage windows. Only control requests are sent."""
    environment = os.environ.copy()
    environment.pop('CLAUDECODE', None)
    if env:
        environment.update(env)
    process = subprocess.Popen(
        [str(executable), '-p', '--input-format', 'stream-json', '--output-format',
         'stream-json', '--verbose', '--no-session-persistence', '--setting-sources',
         '', '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
         '--tools', '', '--settings', '{"disableAllHooks":true}'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, encoding='utf-8', env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
    )
    messages = queue.Queue()

    def read():
        for line in process.stdout:
            try:
                messages.put(json.loads(line))
            except ValueError:
                continue
        messages.put(None)

    threading.Thread(target=read, daemon=True).start()
    deadline = time.monotonic() + timeout

    def request(identifier, payload):
        process.stdin.write(json.dumps({'type': 'control_request', 'request_id': identifier,
                                       'request': payload}) + '\n')
        process.stdin.flush()
        while time.monotonic() < deadline:
            try:
                message = messages.get(timeout=max(.01, deadline - time.monotonic()))
            except queue.Empty:
                break
            if message is None:
                return None
            if not isinstance(message, dict) or message.get('type') != 'control_response':
                continue
            response = message.get('response') or {}
            if response.get('request_id') == identifier:
                return response
        return None

    try:
        init = request('initialize', {'subtype': 'initialize', 'hooks': {}, 'sdkMcpServers': []})
        if not init or init.get('subtype') != 'success':
            return {'ok': False, 'stage': 'initialize'}
        answer = request('usage', {'subtype': 'get_usage', 'skip_behaviors': True})
        if not answer or answer.get('subtype') != 'success':
            return {'ok': False, 'stage': 'usage'}
        data = answer.get('response') or {}
        limits = data.get('rate_limits') or {}
        windows = {}
        for key in WINDOWS:
            window = limits.get(key)
            if not isinstance(window, dict):
                continue
            percent = window.get('utilization')
            if isinstance(percent, (int, float)) and not isinstance(percent, bool) and 0 <= percent <= 100:
                reset = window.get('resets_at')
                windows[key] = {'used_percentage': percent,
                                'resets_at': reset if isinstance(reset, str) and len(reset) <= 80 else None}
        return {'ok': True, 'available': data.get('rate_limits_available') is True,
                'subscription_type': data.get('subscription_type') if isinstance(data.get('subscription_type'), str) else None,
                'windows': windows}
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stdin.close()
        process.stdout.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    parser.add_argument('--executable', type=Path)
    args = parser.parse_args()
    executable = args.executable
    if executable is None:
        executable = find_executable()
    try:
        result = probe(executable) if executable else {'ok': False, 'stage': 'not_installed'}
    except Exception as error:
        result = {'ok': False, 'stage': 'process', 'error_type': type(error).__name__}
    if args.output:
        args.output.write_text(json.dumps(result), encoding='utf-8')
    else:
        print(json.dumps(result))
