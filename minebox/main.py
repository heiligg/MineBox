import curses

from menu import MineBoxApp


def main(screen: curses.window) -> None:
    app = MineBoxApp(screen)
    app.run()


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        print("MineBox stopped safely.")