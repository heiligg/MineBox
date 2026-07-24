import select
import sys
import termios
import time
import tty
from enum import Enum


class InputAction(Enum):
    UP = "up"
    DOWN = "down"
    SELECT = "select"
    BACK = "back"
    QUIT = "quit"
    UNKNOWN = "unknown"
    NONE = "none"


def clear_pending_input(quiet_time: float = 0.20) -> None:
    """
    Clear leftover keyboard input.

    This prevents the Enter key used on one screen from
    accidentally selecting an item on the next screen.
    """
    file_descriptor = sys.stdin.fileno()

    try:
        termios.tcflush(file_descriptor, termios.TCIFLUSH)
    except (termios.error, OSError):
        return

    quiet_started = time.monotonic()

    while True:
        ready, _, _ = select.select(
            [sys.stdin],
            [],
            [],
            0.02,
        )

        if ready:
            try:
                sys.stdin.read(1)
            except OSError:
                return

            quiet_started = time.monotonic()

        if time.monotonic() - quiet_started >= quiet_time:
            return


def get_input(timeout: float | None = None) -> InputAction:
    """
    Read a single keyboard action.

    Controls:
    - Up arrow or W: move up
    - Down arrow or S: move down
    - Enter: select
    - Escape, Backspace, A, or B: back
    - Q: quit
    """
    file_descriptor = sys.stdin.fileno()
    previous_settings = termios.tcgetattr(file_descriptor)

    try:
        tty.setcbreak(file_descriptor)

        ready, _, _ = select.select(
            [sys.stdin],
            [],
            [],
            timeout,
        )

        if not ready:
            return InputAction.NONE

        first_character = sys.stdin.read(1)

        # Arrow keys begin with Escape.
        if first_character == "\x1b":
            ready, _, _ = select.select(
                [sys.stdin],
                [],
                [],
                0.10,
            )

            if not ready:
                return InputAction.BACK

            second_character = sys.stdin.read(1)

            # Common terminal arrow formats:
            # ESC [ A
            # ESC [ B
            # ESC O A
            # ESC O B
            if second_character in ("[", "O"):
                ready, _, _ = select.select(
                    [sys.stdin],
                    [],
                    [],
                    0.10,
                )

                if not ready:
                    return InputAction.UNKNOWN

                third_character = sys.stdin.read(1)

                if third_character == "A":
                    return InputAction.UP

                if third_character == "B":
                    return InputAction.DOWN

            return InputAction.BACK

        if first_character in ("\r", "\n"):
            return InputAction.SELECT

        if first_character in ("\x7f", "\x08"):
            return InputAction.BACK

        lowered_character = first_character.lower()

        if lowered_character == "w":
            return InputAction.UP

        if lowered_character == "s":
            return InputAction.DOWN

        if lowered_character in ("a", "b"):
            return InputAction.BACK

        if lowered_character == "q":
            return InputAction.QUIT

        return InputAction.UNKNOWN

    finally:
        termios.tcsetattr(
            file_descriptor,
            termios.TCSADRAIN,
            previous_settings,
        )