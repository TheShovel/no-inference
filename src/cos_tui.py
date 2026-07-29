#!/usr/bin/env python3
"""
COS TUI — Text User Interface for the Conversation Operating System.

A chat interface to interact with COS directly.
Shows routing decisions, reasoning steps, and timing.
"""

import sys
import os
import time
import readline
import shutil
import textwrap
from pathlib import Path

# Add benchmark directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Colors ───────────────────────────────────────────────────────────────────
class Colors:
    RESET     = '\033[0m'
    BOLD      = '\033[1m'
    DIM       = '\033[2m'
    ITALIC    = '\033[3m'

    # Foreground
    BLACK     = '\033[30m'
    RED       = '\033[31m'
    GREEN     = '\033[32m'
    YELLOW    = '\033[33m'
    BLUE      = '\033[34m'
    MAGENTA   = '\033[35m'
    CYAN      = '\033[36m'
    WHITE     = '\033[37m'

    # Background
    BG_BLACK  = '\033[40m'
    BG_BLUE   = '\033[44m'
    BG_GREEN  = '\033[42m'
    BG_YELLOW = '\033[43m'

    @staticmethod
    def rgb_fg(r, g, b):
        return f'\033[38;2;{r};{g};{b}m'

    @staticmethod
    def rgb_bg(r, g, b):
        return f'\033[48;2;{r};{g};{b}m'

# ── Helpers ──────────────────────────────────────────────────────────────────

def _term_width():
    """Get current terminal width."""
    return shutil.get_terminal_size().columns


def _fill_line(char='─', padding=0):
    """Return a horizontal rule spanning the terminal width."""
    w = _term_width() - padding
    return char * max(w, 1)


def _word_wrap(text, width=None, indent=2):
    """Wrap text to terminal width with indentation."""
    if width is None:
        width = _term_width() - indent
    wrapped = []
    for para in text.split('\n'):
        if para.strip() == '':
            wrapped.append('')
        else:
            wrapped.extend(textwrap.wrap(para, width=width))
    return '\n'.join(' ' * indent + line for line in wrapped)


# ── TUI ──────────────────────────────────────────────────────────────────────

class COSTUI:
    def __init__(self):
        self.conversation_history = []
        self.debug_mode = False
        self.verbose_mode = False

        # Import COS orchestrator handlers from the new modular structure
        try:
            from cos.engine import process_query, detect_intent, reset_conversation, get_conversation_history
            self.process_query = process_query
            self.detect_intent = detect_intent
            self.reset_conversation = reset_conversation
        except ImportError:
            print(f"{Colors.RED}Error: Could not import cos.engine{Colors.RESET}")
            print(f"Make sure src/cos/engine.py exists")
            sys.exit(1)

    def clear_screen(self):
        os.system('clear' if os.name == 'posix' else 'cls')

    def print_banner(self):
        w = _term_width()
        inner_w = w - 4  # space inside the box border
        title = "COS — Conversation Operating System v0.1.0"
        subtitle = "Symbolic Conversational Runtime (no neural nets)"
        help_text = "Type '/help' for commands  |  '/quit' to exit"

        # Dynamic banner that adapts to terminal width
        top = f"╔{'═' * (inner_w)}╗"
        mid1 = f"║ {title:<{inner_w - 1}}║"
        mid2 = f"║ {subtitle:<{inner_w - 1}}║"
        mid3 = f"║{' ' * inner_w}║"
        mid4 = f"║ {help_text:<{inner_w - 1}}║"
        bot = f"╚{'═' * (inner_w)}╝"

        print(f"{Colors.CYAN}{Colors.BOLD}{top}{Colors.RESET}")
        print(f"{Colors.CYAN}{Colors.BOLD}{mid1}{Colors.RESET}")
        print(f"{Colors.CYAN}{Colors.BOLD}{mid2}{Colors.RESET}")
        print(f"{Colors.CYAN}{Colors.BOLD}{mid3}{Colors.RESET}")
        print(f"{Colors.CYAN}{Colors.BOLD}{mid4}{Colors.RESET}")
        print(f"{Colors.CYAN}{Colors.BOLD}{bot}{Colors.RESET}")

    def print_separator(self, char='─'):
        print(f"{Colors.DIM}{_fill_line(char)}{Colors.RESET}")

    def print_system_status(self):
        """Show current system status with real benchmark results."""
        w = _term_width()
        bar_total_width = max(10, min(30, w - 30))

        def _bar(pct):
            bar_len = int(pct / 100 * bar_total_width)
            return '\u2588' * bar_len + '\u2591' * (bar_total_width - bar_len)

        print(f"\n{Colors.DIM}  {Colors.BOLD}NLG Quality{Colors.RESET}  ({Colors.DIM}deterministic{Colors.RESET})")
        nlg_scores = [
            ("Fact Preservation",   99.1, Colors.GREEN),
            ("Coherence",          90.0, Colors.GREEN),
            ("Numerical Precision", 97.4, Colors.GREEN),
            ("Temperature Variety", 70.0, Colors.YELLOW),
            ("Overall",            97.4, Colors.GREEN),
        ]
        for name, pct, color in nlg_scores:
            print(f"  {Colors.DIM}{name:22s}{Colors.RESET} {color}{pct:5.1f}%{Colors.RESET}  {Colors.DIM}{_bar(pct)}{Colors.RESET}")

        print(f"\n{Colors.DIM}  {Colors.BOLD}LLM Judge{Colors.RESET}  ({Colors.DIM}gemma4:31b, 22 cases{Colors.RESET})")
        llm_scores = [
            ("Naturalness",     4.2, Colors.YELLOW),
            ("Informativeness", 6.1, Colors.GREEN),
            ("Coherence",       6.1, Colors.GREEN),
            ("Correctness",     9.3, Colors.GREEN),
            ("Overall",         6.8, Colors.GREEN),
        ]
        for name, score, color in llm_scores:
            pct = score / 10.0 * 100
            print(f"  {Colors.DIM}{name:22s}{Colors.RESET} {color}{score:4.1f}/10{Colors.RESET}  {Colors.DIM}{_bar(pct)}{Colors.RESET}")

        print(f"\n{Colors.DIM}  {Colors.BOLD}Knowledge Base{Colors.RESET}  ({Colors.DIM}curated topics{Colors.RESET})")
        kb_scores = [
            ("Recipes & Cooking",   13, Colors.GREEN),
            ("Home & DIY",          10, Colors.GREEN),
            ("Health & Wellness",    7, Colors.GREEN),
            ("Technology",           8, Colors.GREEN),
            ("Everyday Life",       10, Colors.GREEN),
            ("General Knowledge",   28, Colors.GREEN),
            ("Math Solver",          4, Colors.GREEN),
        ]
        for name, count, color in kb_scores:
            bar = "\u2588" * count + "\u2591" * (28 - count)
            print(f"  {Colors.DIM}{name:22s}{Colors.RESET} {color}{count:2d} topics{Colors.RESET}  {Colors.DIM}{bar}{Colors.RESET}")

        print(f"\n{Colors.DIM}  {Colors.BOLD}Math Solver{Colors.RESET}  ({Colors.DIM}basic arithmetic{Colors.RESET})")
        math_scores = [
            ("Arithmetic",  100.0, Colors.GREEN),
            ("Word Problems", 0.0, Colors.RED),
            ("Overall",      60.0, Colors.YELLOW),
        ]
        for name, pct, color in math_scores:
            print(f"  {Colors.DIM}{name:22s}{Colors.RESET} {color}{pct:5.1f}%{Colors.RESET}  {Colors.DIM}{_bar(pct)}{Colors.RESET}")
        print()

    def show_help(self):
        w = _term_width()
        sep = _fill_line('─', padding=0)
        help_text = f"""
{Colors.BOLD}{Colors.CYAN}  COS Commands{Colors.RESET}
{Colors.DIM}  {sep}{Colors.RESET}
  {Colors.GREEN}/help{Colors.RESET}          Show this help
  {Colors.GREEN}/quit{Colors.RESET}          Exit COS
  {Colors.GREEN}/clear{Colors.RESET}         Clear the screen
  {Colors.GREEN}/debug{Colors.RESET}         Toggle debug output (routing decisions)
  {Colors.GREEN}/verbose{Colors.RESET}       Toggle verbose output (full reasoning)
  {Colors.GREEN}/status{Colors.RESET}        Show benchmark scores
  {Colors.GREEN}/history{Colors.RESET}       Show conversation history
  {Colors.GREEN}/reset{Colors.RESET}         Reset conversation memory
  {Colors.GREEN}/reload{Colors.RESET}        Reload patterns/aliases/templates from disk

{Colors.BOLD}{Colors.CYAN}  Examples{Colors.RESET}
{Colors.DIM}  {sep}{Colors.RESET}
  {Colors.GREEN}hi{Colors.RESET}                    → Greeting
  {Colors.GREEN}What is the capital of France?{Colors.RESET}  → Fact lookup
  {Colors.GREEN}Write a poem about AI{Colors.RESET} → Instruction template
  {Colors.GREEN}Solve: 2 + 3 * 4{Colors.RESET}      → Math solver
  {Colors.GREEN}I like pizza{Colors.RESET}          → Memory storage
  {Colors.GREEN}What do I like?{Colors.RESET}       → Memory recall
  {Colors.GREEN}Pretend to be a pirate{Colors.RESET}→ Roleplay
        """
        print(help_text)

    def _ellipsize(self, text, max_len):
        """Truncate text with ellipsis if it exceeds max_len."""
        if len(text) <= max_len:
            return text
        return text[:max_len - 1] + '…'

    def format_response(self, response, intent, timing):
        """Format a response with optional debug info."""
        w = _term_width()
        output = []

        # Debug info
        if self.debug_mode:
            intent_colors = {
                'factual': Colors.GREEN,
                'math': Colors.MAGENTA,
                'word_problem': Colors.YELLOW,
                'roleplay': Colors.CYAN,
                'instruction': Colors.BLUE,
                'code': Colors.BLUE,
                'follow_up': Colors.CYAN,
            }
            ic = intent_colors.get(intent, Colors.WHITE)

            sep = _fill_line('─', padding=4)
            output.append(f"{Colors.DIM}  ── [{intent}] {'─' * max(2, w - 12 - len(intent))}{Colors.RESET}")
            output.append(f"{Colors.DIM}  Routing: {ic}{intent}{Colors.RESET}  |  {timing:.1f}s{Colors.RESET}")
            output.append(f"{Colors.DIM}  {sep}{Colors.RESET}")

        # The actual response — word-wrapped to terminal width
        if response:
            wrapped = _word_wrap(response, indent=2)
            output.append(wrapped)
        else:
            output.append(f"  {Colors.YELLOW}(empty response){Colors.RESET}")

        return '\n'.join(output)

    def run(self):
        self.clear_screen()

        while True:
            try:
                # Get user input with prompt
                prompt = f"{Colors.BOLD}{Colors.GREEN}❯{Colors.RESET} "
                user_input = input(prompt).strip()

                if not user_input:
                    continue

                # Handle commands
                if user_input.startswith('/'):
                    cmd = user_input[1:].lower()

                    if cmd == 'quit' or cmd == 'exit':
                        print(f"\n{Colors.YELLOW}  Goodbye!{Colors.RESET}\n")
                        break

                    elif cmd == 'help':
                        self.show_help()
                        continue

                    elif cmd == 'clear':
                        self.clear_screen()
                        self.print_banner()
                        continue

                    elif cmd == 'debug':
                        self.debug_mode = not self.debug_mode
                        status = f"{Colors.GREEN}ON{Colors.RESET}" if self.debug_mode else f"{Colors.RED}OFF{Colors.RESET}"
                        print(f"  Debug output: {status}")
                        continue

                    elif cmd == 'verbose':
                        self.verbose_mode = not self.verbose_mode
                        status = f"{Colors.GREEN}ON{Colors.RESET}" if self.verbose_mode else f"{Colors.RED}OFF{Colors.RESET}"
                        print(f"  Verbose output: {status}")
                        continue

                    elif cmd == 'status':
                        self.print_system_status()
                        continue

                    elif cmd == 'history':
                        if not self.conversation_history:
                            print(f"  {Colors.YELLOW}(no conversation history){Colors.RESET}")
                        else:
                            sep = _fill_line('─', padding=2)
                            print(f"\n{Colors.BOLD}{Colors.CYAN}  Conversation History (last 10){Colors.RESET}")
                            print(f"{Colors.DIM}  {sep}{Colors.RESET}")
                            for i, (q, r, intent) in enumerate(self.conversation_history[-10:]):
                                q_display = self._ellipsize(q, 60)
                                r_display = self._ellipsize(r, 60)
                                intent_label = f" [{intent}]" if intent else ""
                                print(f"  {Colors.DIM}#{i+1}{Colors.RESET} {Colors.GREEN}You:{Colors.RESET} {q_display}{Colors.DIM}{intent_label}{Colors.RESET}")
                                print(f"  {Colors.DIM}     {Colors.RESET} {Colors.CYAN}COS:{Colors.RESET} {r_display}")
                        continue

                    elif cmd == 'reset':
                        self.conversation_history = []
                        self.reset_conversation()
                        print(f"  {Colors.GREEN}Conversation memory reset.{Colors.RESET}")
                        continue

                    elif cmd == 'reload':
                        from cos.pattern_matcher import reload as reload_patterns
                        from cos.engine import reload_aliases
                        from cos.template_engine import reload as reload_templates
                        reload_patterns()
                        reload_aliases()
                        reload_templates()
                        print(f"  {Colors.GREEN}Patterns, aliases, and templates reloaded from disk.{Colors.RESET}")
                        continue

                    else:
                        print(f"  {Colors.YELLOW}Unknown command: {user_input}. Type /help for commands.{Colors.RESET}")
                        continue

                # Process query through COS
                start_time = time.time()

                # Detect intent
                intent = self.detect_intent(user_input)

                # Process
                response = self.process_query(user_input, use_cos=True)
                elapsed = time.time() - start_time

                # Store in local history
                self.conversation_history.append((user_input, response[:200], intent))

                # Display response
                formatted = self.format_response(response, intent, elapsed)
                print(formatted)

                # Show timing info
                if self.debug_mode:
                    w = _term_width()
                    print(f"{Colors.DIM}  {_fill_line('─', padding=2)}{Colors.RESET}")
                    print(f"{Colors.DIM}  Response time: {elapsed:.2f}s  |  Length: {len(response)} chars{Colors.RESET}")

            except KeyboardInterrupt:
                print(f"\n{Colors.YELLOW}  Use /quit to exit.{Colors.RESET}")
                continue

            except EOFError:
                print(f"\n{Colors.YELLOW}  Goodbye!{Colors.RESET}\n")
                break

            except Exception as e:
                print(f"\n{Colors.RED}  Error: {e}{Colors.RESET}")
                import traceback
                if self.verbose_mode:
                    traceback.print_exc()


def main():
    """Entry point."""
    tui = COSTUI()
    try:
        tui.run()
    except KeyboardInterrupt:
        print(f"\n  Goodbye!")
    except Exception as e:
        print(f"\n  Fatal error: {e}")
        import traceback
        traceback.print_exc()
    return 0


if __name__ == '__main__':
    main()
