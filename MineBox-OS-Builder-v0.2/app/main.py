import curses

from menu import MineBoxApp


def main(screen: curses.window) -> None:
    app = MineBoxApp(screen)
    try:
        app.run()
    finally:
        try:
            from gpio_buttons import stop_buttons

            stop_buttons()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        print("MineBox stopped safely.")
        try:
            from gpio_buttons import stop_buttons

            stop_buttons()
        except Exception:
            pass
