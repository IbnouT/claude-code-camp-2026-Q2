"""The player task: the main loop's role, playing the MUD."""

from .base import Task


class Player(Task):
    task_name = "player"
