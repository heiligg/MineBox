import os
import time
from typing import Optional


SCREEN_WIDTH = 40


def clear() -> None:
    """
    Clear the terminal screen.
    """
    print("\033[2J\033[H", end="", flush=True)


def draw_header(title: str) -> None:
    """
    Draw a standard MineBox screen header.
    """
    print("=" * SCREEN_WIDTH)
    print(title.center(SCREEN_WIDTH))
    print("=" * SCREEN_WIDTH)


def draw_footer(message: str = "Arrow keys: Move | Enter: Select") -> None:
    """
    Draw a standard footer.
    """
    print("=" * SCREEN_WIDTH)
    print(message[:SCREEN_WIDTH])


def draw_menu(
    title: str,
    options: list[str],
    selected_index: int,
    status_message: Optional[str] = None,
) -> None:
    """
    Draw a selectable menu.
    """
    clear()
    draw_header(title)

    print()

    for index, option in enumerate(options):
        if index == selected_index:
            print(f"> {option}")
        else:
            print(f"  {option}")

    print()

    if status_message:
        print("-" * SCREEN_WIDTH)
        print(status_message[:SCREEN_WIDTH])
        print()

    draw_footer()


def draw_message(
    title: str,
    message: str,
    footer: str = "Press Enter to return",
) -> None:
    """
    Draw a simple message screen.
    """
    clear()
    draw_header(title)
    print()

    for line in message.splitlines():
        print(line[:SCREEN_WIDTH])

    print()
    draw_footer(footer)


def show_temporary_message(
    title: str,
    message: str,
    seconds: float = 2,
) -> None:
    """
    Show a message briefly before returning.
    """
    draw_message(title, message, footer="Please wait...")
    time.sleep(seconds)


def get_terminal_size() -> tuple[int, int]:
    """
    Return terminal columns and rows.
    """
    size = os.get_terminal_size()
    return size.columns, size.lines