#!/usr/bin/env python3
"""
COS Infinite Generator Dashboard — curses TUI for launching and monitoring
the self-discovering knowledge/template generators.

Design:
  - Single command: python3 tools/dashboard.py
  - Auto-refreshes every 2 seconds (no manual refresh needed)
  - Shows live previews of recent generations
  - Shows topic tree growth stats
  - Shows file splitting activity
  - Both generators run independently in the background

Controls:
  [1] Start/stop knowledge generator
  [2] Start/stop template generator
  [3] Start both generators
  [K] Kill all generators
  [Q] Quit
  [Space] Force refresh now
"""

import curses
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime
from collections import defaultdict

ROOT = Path(__file__).parent.parent
TEMPLATE_LOG = ROOT / 'logs' / 'template_gen.log'
KNOWLEDGE_LOG = ROOT / 'logs' / 'knowledge_gen.log'
TRACKING_FILE = ROOT / 'data' / 'knowledge' / '.generated_topics.json'
TEMPLATE_TRACKING = ROOT / 'data' / '.template_tracking.json'
TEMPLATE_DIR = ROOT / 'data' / 'knowledge' / 'templates'
KNOWLEDGE_DIR = ROOT / 'data' / 'knowledge'

# ── Color pair indices ───────────────────────────────────────────────────────
CP_WHITE   = 0
CP_RED     = 1
CP_GREEN   = 2
CP_YELLOW  = 3
CP_BLUE    = 4
CP_CYAN    = 5
CP_MAGENTA = 6

# ── Process management ──────────────────────────────────────────────────────
processes = {}  # name -> subprocess.Popen or None

def _is_running(name):
    proc = processes.get(name)
    if proc is None:
        return False
    if proc.poll() is not None:
        processes[name] = None
        return False
    return True

def _start_generator(name, cmd, log_path):
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

def _stop_all():
    for name in list(processes.keys()):
        _stop_generator(name)

def _get_pid(name):
    proc = processes.get(name)
    if proc and proc.poll() is None:
        return proc.pid
    return None

# ── Data loading ────────────────────────────────────────────────────────────

def _load_json(path):
    if path and path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return None

def _count_json_files(directory):
    """Count JSON files recursively, excluding hidden files."""
    if not directory.exists():
        return 0
    return sum(1 for p in directory.rglob('*.json') if not p.name.startswith('.'))

def _count_entries_in_files(directory):
    """Count total JSON entries across all files in a directory."""
    total = 0
    if not directory.exists():
        return 0
    for path in directory.rglob('*.json'):
        if path.name.startswith('.'):
            continue
        try:
            data = json.loads(path.read_text())
            if isinstance(data, list):
                total += len(data)
            elif isinstance(data, dict):
                total += 1
        except Exception:
            pass
    return total

def _get_file_split_stats(directory):
    """Count how many topics have been split into multiple files."""
    if not directory.exists():
        return 0, 0
    files = [p for p in directory.rglob('*.json') if not p.name.startswith('.')]
    # Group files by base name (ignoring trailing digits)
    groups = defaultdict(list)
    for f in files:
        stem = f.stem
        base = re.sub(r'\d+$', '', stem) if stem else stem
        groups[base].append(f)
    multi_file = sum(1 for g in groups.values() if len(g) > 1)
    return multi_file, len(groups)

def _get_latest_log(log_path, max_lines=15):
    """Get the last N lines from a log file."""
    if not log_path.exists():
        return []
    try:
        text = log_path.read_text()
        lines = text.strip().split('\n')
        return lines[-max_lines:]
    except Exception:
        return []

def _get_topic_tree_depth(tracking):
    """Calculate average and max depth of the topic tree."""
    if not tracking:
        return 0, 0
    topics = tracking.get("topics", {})
    depths = [info.get("depth", 0) for info in topics.values()]
    if not depths:
        return 0, 0
    return max(depths), sum(depths) / len(depths)

# ── UI helpers ──────────────────────────────────────────────────────────────

def _safe_addstr(win, y, x, text, attr=0):
    """Write to curses window with bounds checking. Silently skips if out of bounds."""
    height, width = win.getmaxyx()
    if y < 0 or y >= height or x < 0 or x >= width:
        return
    max_len = width - x
    if max_len <= 0:
        return
    display = text[:max_len] if len(text) > max_len else text
    try:
        if attr:
            win.addstr(y, x, display, attr)
        else:
            win.addstr(y, x, display)
    except curses.error:
        pass


def _draw_section_header(win, y, x, text, width):
    """Draw a section header with horizontal rule, e.g. '─── Controls ───'."""
    avail = max(3, width - x)
    label = f" {text} "
    dash_total = avail - len(label)
    left = dash_total // 2
    right = dash_total - left
    line = '─' * left + label + '─' * right
    _safe_addstr(win, y, x, line, curses.color_pair(CP_CYAN) | curses.A_BOLD)


def _draw_progress_bar(win, y, x, bar_width, pct, label=""):
    """Draw a progress bar."""
    filled = int(bar_width * pct / 100)
    bar = '█' * filled + '░' * (bar_width - filled)
    _safe_addstr(win, y, x, f"{label} [{bar}] {pct:.0f}%")


# ── Main ────────────────────────────────────────────────────────────────────

def _main(stdscr):
    curses.curs_set(0)
    curses.use_default_colors()

    # Initialize color pairs
    curses.init_pair(CP_RED,     curses.COLOR_RED,     -1)
    curses.init_pair(CP_GREEN,   curses.COLOR_GREEN,   -1)
    curses.init_pair(CP_YELLOW,  curses.COLOR_YELLOW,  -1)
    curses.init_pair(CP_BLUE,    curses.COLOR_BLUE,    -1)
    curses.init_pair(CP_CYAN,    curses.COLOR_CYAN,    -1)
    curses.init_pair(CP_MAGENTA, curses.COLOR_MAGENTA, -1)

    stdscr.nodelay(1)  # Non-blocking input
    refresh_interval = 2  # Auto-refresh every 2 seconds

    # Auto-detect backend: prefer Ollama if available, fall back to template
    backend = "template"
    backend_model = ""
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            if resp.status == 200:
                backend = "ollama"
                backend_model = "gemma4:31b-cloud"
    except Exception:
        pass

    # Build backend args for subprocess calls
    be_args = ["--backend", backend]
    if backend_model:
        be_args += ["--model", backend_model]
    backend_label = f"Ollama ({backend_model})" if backend == "ollama" else "Template (no LLM)"

    last_refresh = time.time()
    last_preview_update = time.time()
    preview_buffer = {"knowledge": [], "template": []}

    while True:
        now = time.time()
        height, width = stdscr.getmaxyx()

        # ── Clear and redraw every cycle ─────────────────────────────────
        stdscr.erase()

        # ── Header (full-width reversed) ─────────────────────────────────
        title = "COS Generator Dashboard — Infinite Mode"
        try:
            _safe_addstr(stdscr, 0, max(0, (width - len(title)) // 2), title,
                          curses.A_BOLD | curses.A_REVERSE)
        except Exception:
            pass

        # ── Status line ─────────────────────────────────────────────────
        ts = datetime.now().strftime('%H:%M:%S')
        status_text = f"  {ts}  |  Backend: {backend_label}  |  [Space] refresh  |  [Q]uit"
        # Truncate if too long
        if len(status_text) > width:
            status_text = status_text[:width]
        _safe_addstr(stdscr, 1, 0, status_text)

        # ── Generator Controls ──────────────────────────────────────────
        row = 3
        _draw_section_header(stdscr, row, 0, "Controls", width)
        row += 1

        k_running = _is_running("knowledge_gen")
        t_running = _is_running("template_gen")

        k_status = "● RUNNING" if k_running else "○ stopped"
        t_status = "● RUNNING" if t_running else "○ stopped"
        k_color = curses.color_pair(CP_GREEN) if k_running else curses.color_pair(CP_YELLOW)
        t_color = curses.color_pair(CP_GREEN) if t_running else curses.color_pair(CP_YELLOW)

        _safe_addstr(stdscr, row, 2, "[1]", curses.A_BOLD)
        _safe_addstr(stdscr, row, 5, f" Knowledge gen: {k_status}", k_color)
        if k_running:
            _safe_addstr(stdscr, row, 35, f" PID:{_get_pid('knowledge_gen')}")
        row += 1

        _safe_addstr(stdscr, row, 2, "[2]", curses.A_BOLD)
        _safe_addstr(stdscr, row, 5, f" Template gen:  {t_status}", t_color)
        if t_running:
            _safe_addstr(stdscr, row, 35, f" PID:{_get_pid('template_gen')}")
        row += 1

        _safe_addstr(stdscr, row, 2, "[3]", curses.A_BOLD)
        _safe_addstr(stdscr, row, 5, " Start both")
        row += 1

        _safe_addstr(stdscr, row, 2, "[K]", curses.A_BOLD)
        _safe_addstr(stdscr, row, 5, " Kill all")
        row += 1

        # ── Knowledge Stats ─────────────────────────────────────────────
        row += 1
        _draw_section_header(stdscr, row, 0, "Knowledge Base Growth", width)
        row += 1

        tracking = _load_json(TRACKING_FILE)
        k_files = _count_json_files(KNOWLEDGE_DIR)
        k_entries = _count_entries_in_files(KNOWLEDGE_DIR)

        if tracking:
            topics = tracking.get("topics", {})
            total_gen = tracking.get("total_generated", 0)
            max_depth, avg_depth = _get_topic_tree_depth(tracking)
            multi_split, total_bases = _get_file_split_stats(KNOWLEDGE_DIR)

            _safe_addstr(stdscr, row, 2, f"Total entries:     {k_entries}  (tracked: {total_gen})")
            row += 1
            _safe_addstr(stdscr, row, 2, f"Total files:       {k_files}")
            row += 1
            _safe_addstr(stdscr, row, 2, f"Topics discovered: {len(topics)}")
            row += 1
            _safe_addstr(stdscr, row, 2, f"Tree depth:        max={max_depth}  avg={avg_depth:.1f}")
            row += 1
            _safe_addstr(stdscr, row, 2, f"Multi-file topics: {multi_split}/{total_bases}")
            row += 1

            # Category breakdown
            cats = tracking.get("categories", {})
            if cats:
                row += 1
                _safe_addstr(stdscr, row, 2, "Categories:")
                row += 1
                bar_max = max(10, width - 35)  # dynamic bar width
                for cat_name in sorted(cats.keys()):
                    if row >= height - 2:
                        _safe_addstr(stdscr, row, 2, "... (more categories off screen)", curses.color_pair(CP_YELLOW))
                        row += 1
                        break
                    info = cats[cat_name]
                    bar_count = info.get("count", 0)
                    bar_len = min(bar_count, bar_max)
                    bar = '█' * bar_len
                    _safe_addstr(stdscr, row, 4, f"{cat_name:15s} {bar_count:5d} entries {bar}")
                    row += 1
        else:
            _safe_addstr(stdscr, row, 2, "No knowledge data yet. Start the generator!",
                          curses.color_pair(CP_YELLOW))
            row += 1

        # ── Template Stats ──────────────────────────────────────────────
        row += 1
        _draw_section_header(stdscr, row, 0, "Template Growth", width)
        row += 1

        tmpl_tracking = _load_json(TEMPLATE_TRACKING)
        t_files = _count_json_files(TEMPLATE_DIR)
        t_entries = _count_entries_in_files(TEMPLATE_DIR)

        if tmpl_tracking:
            templates = tmpl_tracking.get("templates", {})
            total_tmpl = tmpl_tracking.get("total_generated", 0)

            _safe_addstr(stdscr, row, 2, f"Total entries:     {t_entries}  (tracked: {total_tmpl})")
            row += 1
            _safe_addstr(stdscr, row, 2, f"Total files:       {t_files}")
            row += 1
            _safe_addstr(stdscr, row, 2, f"Template types:    {len(templates)}")
            row += 1
        else:
            _safe_addstr(stdscr, row, 2, "No template data yet. Start the generator!",
                          curses.color_pair(CP_YELLOW))
            row += 1

        # ── Live Generation Previews ────────────────────────────────────
        if now - last_preview_update >= 3:
            last_preview_update = now
            preview_buffer["knowledge"] = _get_latest_log(KNOWLEDGE_LOG, 8)
            preview_buffer["template"] = _get_latest_log(TEMPLATE_LOG, 8)

        row += 1
        _draw_section_header(stdscr, row, 0, "Live Output Preview", width)

        # Knowledge preview
        row += 1
        if preview_buffer["knowledge"]:
            _safe_addstr(stdscr, row, 2, "Knowledge gen:", curses.A_BOLD)
            row += 1
            for line in preview_buffer["knowledge"][-6:]:
                if row >= height - 1:
                    _safe_addstr(stdscr, row, 4, "... (more lines off screen)", curses.color_pair(CP_YELLOW))
                    row += 1
                    break
                display = line[:width - 4] if len(line) > width - 4 else line
                if "✓" in line or "Wrote" in line:
                    _safe_addstr(stdscr, row, 4, display, curses.color_pair(CP_GREEN))
                elif "FAILED" in line or "Error" in line:
                    _safe_addstr(stdscr, row, 4, display, curses.color_pair(CP_RED))
                else:
                    _safe_addstr(stdscr, row, 4, display)
                row += 1
        else:
            _safe_addstr(stdscr, row, 2, "Knowledge gen: (no output yet)", curses.color_pair(CP_YELLOW))
            row += 1

        # Template preview
        row += 1
        if preview_buffer["template"]:
            _safe_addstr(stdscr, row, 2, "Template gen:", curses.A_BOLD)
            row += 1
            for line in preview_buffer["template"][-6:]:
                if row >= height - 1:
                    _safe_addstr(stdscr, row, 4, "... (more lines off screen)", curses.color_pair(CP_YELLOW))
                    row += 1
                    break
                display = line[:width - 4] if len(line) > width - 4 else line
                if "✓" in line or "Wrote" in line:
                    _safe_addstr(stdscr, row, 4, display, curses.color_pair(CP_GREEN))
                elif "FAILED" in line or "Error" in line:
                    _safe_addstr(stdscr, row, 4, display, curses.color_pair(CP_RED))
                else:
                    _safe_addstr(stdscr, row, 4, display)
                row += 1
        else:
            _safe_addstr(stdscr, row, 2, "Template gen: (no output yet)", curses.color_pair(CP_YELLOW))
            row += 1

        # ── Handle Input ────────────────────────────────────────────────
        key = stdscr.getch()
        if key != -1:
            if key == ord('1'):
                if not _is_running("knowledge_gen"):
                    cmd = [
                        sys.executable, '-u', str(ROOT / 'tools' / 'knowledge_generator.py'),
                        '--mode', 'continuous',
                        '--interval', '3', '--count', '5',
                    ] + be_args
                    _start_generator("knowledge_gen", cmd, KNOWLEDGE_LOG)
                else:
                    _stop_generator("knowledge_gen")
            elif key == ord('2'):
                if not _is_running("template_gen"):
                    cmd = [
                        sys.executable, '-u', str(ROOT / 'tools' / 'knowledge_generator.py'),
                        '--type', 'template', '--mode', 'continuous',
                        '--interval', '3', '--count', '5',
                    ] + be_args
                    _start_generator("template_gen", cmd, TEMPLATE_LOG)
                else:
                    _stop_generator("template_gen")
            elif key == ord('3'):
                if not _is_running("knowledge_gen"):
                    cmd = [
                        sys.executable, '-u', str(ROOT / 'tools' / 'knowledge_generator.py'),
                        '--mode', 'continuous',
                        '--interval', '3', '--count', '5',
                    ] + be_args
                    _start_generator("knowledge_gen", cmd, KNOWLEDGE_LOG)
                if not _is_running("template_gen"):
                    cmd = [
                        sys.executable, '-u', str(ROOT / 'tools' / 'knowledge_generator.py'),
                        '--type', 'template', '--mode', 'continuous',
                        '--interval', '4', '--count', '5',
                    ] + be_args
                    _start_generator("template_gen", cmd, TEMPLATE_LOG)
            elif key == ord('k') or key == ord('K'):
                _stop_all()
            elif key == ord('q') or key == ord('Q'):
                _stop_all()
                break
            elif key == ord(' '):
                last_refresh = 0  # Force refresh

        # ── Flush updates to screen ─────────────────────────────────────
        stdscr.refresh()

        # Brief sleep to prevent busy-looping
        time.sleep(0.1)


def main():
    try:
        curses.wrapper(_main)
    except KeyboardInterrupt:
        _stop_all()
    except Exception as e:
        _stop_all()
        print(f"Dashboard error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
