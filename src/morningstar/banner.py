"""MorningStar CLI banner and branding."""

from rich.console import Console
from rich.text import Text

STAR = (
    "            .          \n"
    "           /|\\         \n"
    "          / | \\        \n"
    "         /  |  \\       \n"
    "    ----'   |   '----  \n"
    "     \\      |      /   \n"
    "      \\     |     /    \n"
    "       \\    |    /     \n"
    "        \\   |   /      \n"
    "         \\  |  /       \n"
    "          \\ | /        \n"
    "           \\|/         \n"
    "            '          "
)

BANNER_TEXT = (
    " __  __  ___  ___ _  _ ___ _  _  ___ ___ _____ _   ___  \n"
    "|  \\/  |/ _ \\| _ \\ \\| |_ _| \\| |/ __/ __|_   _/_\\ | _ \\\n"
    "| |\\/| | (_) |   / .` || || .` | (_ \\__ \\ | |/ _ \\|   /\n"
    "|_|  |_|\\___/|_|_\\_|\\_|___|_|\\_|\\___|___/ |_/_/ \\_\\_|_\\"
)


def print_banner(console: Console) -> None:
    """Print the MorningStar startup banner."""
    star_text = Text(STAR, style="bold yellow")
    console.print(star_text, justify="center")

    banner = Text(BANNER_TEXT, style="bold bright_yellow")
    console.print(banner, justify="center")
    console.print()

    tagline = Text(
        "Autonomous Coding Agent  ·  Powered by Claude Code",
        style="dim white",
    )
    console.print(tagline, justify="center")
    console.print()
