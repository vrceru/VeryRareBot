import platform
import socket

from core.version import get_version


def line():
    print("=" * 60)


def section(title):
    print()
    print(title)
    print("─" * 60)


def status(name, value="OK"):
    print(f"[ {value} ] {name}")


def startup_banner():

    line()

    print(
        f"{'VeryRareBot v' + get_version():^60}"
    )

    print(
        f"{'Very Rare Society Assistant':^60}"
    )

    line()


    section("Startup")

    status("Configuration loaded")
    status("Logging initialized")
    status("Permissions loaded")


    section("System")

    print(
        f"Host       : {socket.gethostname()}"
    )

    print(
        f"OS         : {platform.system()} {platform.release()}"
    )

    print(
        f"Python     : {platform.python_version()}"
    )


def ready_banner(bot):

    section("Discord")

    print(
        f"Bot Name   : {bot.user}"
    )

    print(
        f"Guilds     : {len(bot.guilds)}"
    )

    print(
        f"Latency    : {round(bot.latency * 1000)} ms"
    )


    line()

    print(
        "Ready for commands."
    )

    line()
