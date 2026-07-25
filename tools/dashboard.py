#!/usr/bin/env python3
"""
COS Generator Dashboard — TUI for launching and tracking knowledge/template generation.

Single command to start everything:
  python3 tools/dashboard.py

Controls:
  [1] Start/stop template generator
  [2] Start/stop knowledge generator
  [3] Start both
  [K] Kill all
  [R] Refresh
  [Q] Quit
"""

import curses
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent
TEMPLATE_LOG = ROOT / 'logs' / 'template_gen.log'
KNOWLEDGE_LOG = ROOT / 'logs' / 'knowledge_gen.log'
TRACKING_FILE = ROOT / 'data' / '.generated_topics.json'
TEMPLATE_TRACKING = ROOT / 'data' / '.template_tracking.json'
TEMPLATE_DIR = ROOT / 'data' / 'knowledge' / 'templates'
KNOWLEDGE_DIR = ROOT / 'data' / 'knowledge'

# ── Process management ──────────────────────────────────────────────────────

processes = {}  # name -> subprocess.Popen or None


def _is_running(name):
    """Check if a generator process is running."""
    proc = processes.get(name)
    if proc is None:
        return False
    if proc.poll() is not None:
        processes[name] = None
        return False
    return True


def _start_generator(name, cmd, log_path):
    """Start a generator in the background."""
    if _is_running(name):
        return False
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, 'w') as f:
        proc = subprocess.Popen(
            cmd,
            stdout=f,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid,
        )
    processes[name] = proc
    return True


def _stop_generator(name):
    """Stop a generator process."""
    proc = processes.get(name)
    if proc is None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    processes[name] = None


def _get_pid(name):
    """Get PID of a generator process."""
    proc = processes.get(name)
    if proc and proc.poll() is None:
        return proc.pid
    return None


def _stop_all():
    _stop_generator('template')
    _stop_generator('knowledge')


# ── Data loading ─────────────────────────────────────────────────────────────

def _load_json(path):
    try:
        return json.loads(path.read_text())
    except:
        return {}


def _count_json_files(directory):
    """Count non-empty JSON files in a directory tree."""
    count = 0
    entries = 0
    for path in sorted(directory.rglob('*.json')):
        if path.name.startswith('.'):
            continue
        count += 1
        try:
            data = json.loads(path.read_text())
            if isinstance(data, list):
                entries += len(data)
        except:
            pass
    return count, entries


# ── Coverage data ────────────────────────────────────────────────────────────

TEMPLATE_CATEGORIES = {
    "actions": {"write": 9, "explain": 7, "create": 5, "code": 5, "analyze": 5},
    "conversation": {"followups": 4, "opinions": 5, "clarifications": 4, "meta": 4},
    "agentic": {"research": 4, "plan": 4, "brainstorm": 4, "critique": 4, "teach": 4, "debate": 3, "advise": 4},
    "contextual": {"references": 5, "continuation": 4, "elaboration": 4, "transformation": 4, "summarization": 4},
}

KNOWLEDGE_CATEGORIES = {
    "science": 87, "geography": 24, "history": 44, "technology": 39,
    "conversation": 10, "arts": 25, "health": 17, "nature": 23, "daily_life": 19,
}


def _get_template_coverage(tracking):
    """Get coverage stats for template types."""
    covered = tracking.get("templates", {})
    results = {}
    for cat, types in TEMPLATE_CATEGORIES.items():
        total = sum(types.values())
        done = sum(1 for k in covered if k.startswith(cat + "."))
        results[cat] = (done, total)
    return results


def _get_knowledge_coverage(tracking):
    """Get coverage stats for knowledge topics."""
    covered = tracking.get("topics", {})
    results = {}
    for cat, total in KNOWLEDGE_CATEGORIES.items():
        done = sum(1 for k in covered if k.startswith(cat + "."))
        results[cat] = (done, total)
    return results


def _get_latest_log(log_path, n=3):
    """Get last n lines from a log file."""
    if not log_path.exists():
        return []
    try:
        lines = log_path.read_text().splitlines()
        return lines[-n:]
    except:
        return []


# ── Dashboard ────────────────────────────────────────────────────────────────

def _draw_progress_bar(win, y, x, width, done, total, label=""):
    """Draw a progress bar at (y, x)."""
    pct = (done / total * 100) if total > 0 else 0
    filled = int(pct / 100 * (width - 10))
    bar = "█" * filled + "░" * (width - 10 - filled)
    text = f" {label}{done}/{total} {pct:3.0f}%"
    try:
        win.addstr(y, x, bar, curses.color_pair(3) if pct < 50 else curses.color_pair(2) if pct < 80 else curses.color_pair(4))
        win.addstr(y, x + width - 10, text[:30])
    except:
        pass


def _main(stdscr):
    curses.curs_set(0)
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_CYAN, -1)
    curses.init_pair(2, curses.COLOR_GREEN, -1)
    curses.init_pair(3, curses.COLOR_YELLOW, -1)
    curses.init_pair(4, curses.COLOR_BLUE, -1)
    curses.init_pair(5, curses.COLOR_RED, -1)
    curses.init_pair(6, curses.COLOR_MAGENTA, -1)

    height, width = stdscr.getmaxyx()

    last_refresh = 0
    refresh_interval = 2  # seconds
    template_interval = 0  # no wait — generate continuously
    knowledge_interval = 0  # no wait — generate continuously

    stdscr.nodelay(1)  # Non-blocking getch — auto-refresh works

    while True:
        now = time.time()
        if now - last_refresh > refresh_interval:
            try:
                stdscr.clear()
            except:
                pass
            last_refresh = now
            height, width = stdscr.getmaxyx()
            bar_width = min(width - 15, 60)
            if bar_width < 10:
                bar_width = 10

            # ── Title ──
            try:
                title = "COS Generator Dashboard"
                stdscr.addstr(0, max(0, (width - len(title)) // 2), title, curses.A_BOLD | curses.color_pair(1))
                stdscr.addstr(1, 0, "─" * min(width, 100), curses.color_pair(3))
            except:
                pass

            # ── Generator Status ──
            row = 3
            try:
                stdscr.addstr(row, 0, "  GENERATORS", curses.A_BOLD)
            except:
                pass
            row += 1

            # Load tracking data
            t_tracking = _load_json(TEMPLATE_TRACKING) if TEMPLATE_TRACKING.exists() else {}
            k_tracking = _load_json(TRACKING_FILE) if TRACKING_FILE.exists() else {}

            # Template generator
            t_running = _is_running('template')
            t_pid = _get_pid('template')
            t_status = f"RUNNING (PID {t_pid})" if t_running else "STOPPED"
            t_color = curses.color_pair(2) if t_running else curses.color_pair(5)
            t_total = t_tracking.get('total_generated', 0)
            t_tcount, t_entries = _count_json_files(TEMPLATE_DIR)
            try:
                stdscr.addstr(row, 2, "[1] Template Generator:", curses.A_BOLD)
                if row < height:
                    stdscr.addstr(row, 26, t_status, t_color)
                    stdscr.addstr(row, min(46, width-20), f"  {t_entries} entries in {t_tcount} files")
            except:
                pass
            row += 1

            # Knowledge generator
            k_running = _is_running('knowledge')
            k_pid = _get_pid('knowledge')
            k_status = f"RUNNING (PID {k_pid})" if k_running else "STOPPED"
            k_color = curses.color_pair(2) if k_running else curses.color_pair(5)
            k_total = k_tracking.get('total_generated', 0)
            k_tcount, k_entries = _count_json_files(KNOWLEDGE_DIR)
            try:
                stdscr.addstr(row, 2, "[2] Knowledge Generator:", curses.A_BOLD)
                if row < height:
                    stdscr.addstr(row, 26, k_status, k_color)
                    stdscr.addstr(row, min(46, width-20), f"  {k_entries} entries in {k_tcount} files")
            except:
                pass
            row += 2

            # ── Template Coverage ──
            try:
                stdscr.addstr(row, 0, "  TEMPLATE COVERAGE", curses.A_BOLD)
            except: pass
            row += 1
            t_coverage = _get_template_coverage(t_tracking)
            for cat, (done, total) in t_coverage.items():
                if row >= height - 2:
                    break
                try:
                    _draw_progress_bar(stdscr, row, 2, bar_width, done, total, f"{cat:15s}")
                except: pass
                row += 1

            row += 1

            # ── Knowledge Coverage ──
            if row < height - 2:
                try:
                    stdscr.addstr(row, 0, "  KNOWLEDGE COVERAGE", curses.A_BOLD)
                except: pass
                row += 1
                k_coverage = _get_knowledge_coverage(k_tracking)
                for cat, (done, total) in k_coverage.items():
                    if row >= height - 2:
                        break
                    try:
                        _draw_progress_bar(stdscr, row, 2, bar_width, done, total, f"{cat:15s}")
                    except: pass
                    row += 1

            row += 1

            # ── Live Preview (latest generated entry) ──
            try:
                if row < height - 12:
                    stdscr.addstr(row, 0, "  LATEST PREVIEW", curses.A_BOLD)
                    row += 1

                    # Find most recently modified template file
                    t_files = sorted(TEMPLATE_DIR.rglob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
                    if t_files:
                        try:
                            data = json.loads(t_files[0].read_text())
                            if isinstance(data, list) and data:
                                last = data[-1]
                                triggers = last.get('triggers', ['?'])
                                t_text = last.get('template', '')[:width-20]
                                trig_text = triggers[0][:width-30] if triggers else '?'
                                fname = str(t_files[0].relative_to(TEMPLATE_DIR))[:width-20]
                                stdscr.addstr(row, 2, f"Template: [{fname}]", curses.color_pair(1))
                                row += 1
                                stdscr.addstr(row, 4, f"Trigger: \"{trig_text}\"")
                                row += 1
                                if t_text:
                                    preview_line = t_text[:width-6].replace('\n', ' ')
                                    stdscr.addstr(row, 4, f"Preview: {preview_line}")
                                    row += 1
                        except: pass

                    row += 1

                    # Find most recently modified knowledge file
                    k_files = sorted(KNOWLEDGE_DIR.rglob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
                    k_files = [f for f in k_files if 'templates' not in str(f) and not f.name.startswith('.')]
                    if k_files:
                        try:
                            data = json.loads(k_files[0].read_text())
                            if isinstance(data, list) and data:
                                last = data[-1]
                                qs = last.get('q', last.get('patterns', ['?']))
                                a_text = last.get('a', last.get('answer', ''))[:width-20]
                                q_text = qs[0][:width-30] if qs else '?'
                                fname = str(k_files[0].relative_to(KNOWLEDGE_DIR))[:width-20]
                                stdscr.addstr(row, 2, f"Knowledge: [{fname}]", curses.color_pair(1))
                                row += 1
                                stdscr.addstr(row, 4, f"Q: \"{q_text}\"")
                                row += 1
                                if a_text:
                                    preview_line = a_text[:width-6].replace('\n', ' ')
                                    stdscr.addstr(row, 4, f"A: {preview_line}")
                                    row += 1
                        except: pass
            except: pass

            # ── Recent Logs ──
            try:
                if row < height - 6:
                    stdscr.addstr(row, 0, "  RECENT LOGS", curses.A_BOLD)
                    row += 1
                    t_logs = _get_latest_log(TEMPLATE_LOG, 2)
                    k_logs = _get_latest_log(KNOWLEDGE_LOG, 2)
                    stdscr.addstr(row, 2, "Template:", curses.color_pair(1))
                    if t_logs:
                        for line in t_logs:
                            if row >= height - 2:
                                break
                            display = line[:width-4] if len(line) > width-4 else line
                            stdscr.addstr(row, 12, display[:width-12])
                            row += 1
                    else:
                        stdscr.addstr(row, 12, "(idle)")
                        row += 1
                    row += 1
                    stdscr.addstr(row, 2, "Knowledge:", curses.color_pair(1))
                    if k_logs:
                        for line in k_logs:
                            if row >= height - 2:
                                break
                            display = line[:width-4] if len(line) > width-4 else line
                            stdscr.addstr(row, 12, display[:width-12])
                            row += 1
                    else:
                        stdscr.addstr(row, 12, "(idle)")
                        row += 1
            except: pass

            # ── Controls ──
            try:
                row = height - 3
                controls = "[1] Template  [2] Knowledge  [3] Both  [K] Kill All  [R] Refresh  [Q] Quit"
                if len(controls) > width - 2:
                    controls = "[1]T [2]K [3]Both [K]Kill [R]Ref [Q]Quit"
                stdscr.addstr(row, max(0, (width - len(controls)) // 2), controls, curses.A_DIM)
                stdscr.addstr(row + 1, 0, "─" * min(width, 100), curses.color_pair(3))
            except: pass

            try:
                stdscr.refresh()
            except: pass

        # ── Key handling ──
        key = stdscr.getch()
        if key == -1:  # No key pressed (nodelay mode)
            continue

        if key == ord('q') or key == ord('Q'):
            _stop_all()
            break

        elif key == ord('k') or key == ord('K'):
            _stop_all()

        elif key == ord('r') or key == ord('R'):
            last_refresh = 0  # Force refresh

        elif key == ord('1'):
            if _is_running('template'):
                _stop_generator('template')
            else:
                cmd = [
                    sys.executable, '-u', str(ROOT / 'tools' / 'knowledge_generator.py'),
                    '--type', 'template', '--mode', 'continuous',
                    '--interval', str(template_interval), '--count', '5',
                    '--backend', 'ollama', '--model', 'gemma4:31b-cloud',
                ]
                _start_generator('template', cmd, TEMPLATE_LOG)

        elif key == ord('2'):
            if _is_running('knowledge'):
                _stop_generator('knowledge')
            else:
                cmd = [
                    sys.executable, '-u', str(ROOT / 'tools' / 'knowledge_generator.py'),
                    '--mode', 'continuous',
                    '--interval', str(knowledge_interval), '--count', '5',
                    '--backend', 'ollama', '--model', 'gemma4:31b-cloud',
                ]
                _start_generator('knowledge', cmd, KNOWLEDGE_LOG)

        elif key == ord('3'):
            if not _is_running('template'):
                cmd = [
                    sys.executable, '-u', str(ROOT / 'tools' / 'knowledge_generator.py'),
                    '--type', 'template', '--mode', 'continuous',
                    '--interval', str(template_interval), '--count', '5',
                    '--backend', 'ollama', '--model', 'gemma4:31b-cloud',
                ]
                _start_generator('template', cmd, TEMPLATE_LOG)
            if not _is_running('knowledge'):
                cmd = [
                    sys.executable, '-u', str(ROOT / 'tools' / 'knowledge_generator.py'),
                    '--mode', 'continuous',
                    '--interval', str(knowledge_interval), '--count', '5',
                    '--backend', 'ollama', '--model', 'gemma4:31b-cloud',
                ]
                _start_generator('knowledge', cmd, KNOWLEDGE_LOG)

        elif key == ord('5'):
            template_interval = max(0, template_interval - 1)
        elif key == ord('6'):
            template_interval = min(30, template_interval + 1)
        elif key == ord('7'):
            knowledge_interval = max(0, knowledge_interval - 1)
        elif key == ord('8'):
            knowledge_interval = min(30, knowledge_interval + 1)


def main():
    try:
        curses.wrapper(_main)
    except KeyboardInterrupt:
        _stop_all()
    except Exception as e:
        _stop_all()
        print(f"Error: {e}")
    finally:
        print("\nDashboard closed.")


if __name__ == "__main__":
    main()
