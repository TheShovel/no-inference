"""A tiny command-line todo app. Fill in the empty bodies."""

TODO = []
DONE = []


def add_task(text):
    ...


def list_tasks():
    ...


def mark_done(index):
    # TODO: move the task at index from TODO to DONE
    ...


def count_remaining():
    # TODO: return the number of unfinished tasks
    ...


def clear_finished():
    ...


def main():
    while True:
        try:
            cmd = input('todo> ').strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not cmd:
            continue
        parts = cmd.split(' ', 1)
        verb = parts[0].lower()
        rest = parts[1] if len(parts) > 1 else ''
        if verb == 'add':
            add_task(rest)
        elif verb == 'done':
            mark_done(int(rest))
        elif verb == 'list':
            list_tasks()
        elif verb == 'clear':
            clear_finished()
        elif verb == 'quit':
            break
        else:
            print(f'unknown command: {verb}')


if __name__ == '__main__':
    main()
