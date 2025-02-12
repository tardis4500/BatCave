"""This module provides utilities for creating command line menus."""

# Import standard modules
from dataclasses import dataclass
from typing import cast, List, override


@dataclass(frozen=True)
class MenuItem:
    """Class to represent a single menu item.

        Attributes:
            key: The key input for the menu selection.
            desc: The text description for the menu selection.
    """
    key: str
    desc: str


@dataclass
class Menu:
    """Class to create a universal abstract interface for a command-line menu.

        Attributes:
            items: The list of items for the menu.
            title (optional, default=_DEFAULT_TITLE): The title for the menu.
            prompt (optional, default=_DEFAULT_PROMPT): The prompt for the menu.
            invalid_msg (optional, default=_DEFAULT_INVALID_MESSAGE): The invalid choice message.
            multiselect (optional, default=False): If True, multiple options can be selected.
            ignorecase (optional, default=True): If True, menu input will be case insensitive.
    """
    items: List[MenuItem]
    title: str = '\nSelect one of the following\n'
    prompt: str = '-> '
    invalid_msg: str = '\nInvalid choice\n'
    multiselect: bool = False
    ignorecase: bool = True

    def show(self) -> str | List[str]:
        """Show the menu.

        Returns:
            The choice selected from the menu.
        """
        invalid_choice = True
        valid_choices = []
        menu = self.title + '\n'
        for item in self.items:
            valid_choices.append(item.key.upper() if self.ignorecase else item.key)
            menu += f'\t{item.key}. {item.desc}\n'

        choices = []
        while invalid_choice:
            print(menu)

            choices = [c.strip() for c in input(self.prompt).split(',')]
            if self.ignorecase:
                choices = [c.upper() for c in choices]

            invalid_choice = False
            for choice in choices:
                if choice not in valid_choices:
                    invalid_choice = True
            if not choices:
                invalid_choice = True
            if invalid_choice:
                print(self.invalid_msg)
        print()
        return choices if self.multiselect else choices[0]


@dataclass
class SimpleMenu(Menu):
    """A simplified version of the Menu class.

        Attributes:
            return_text (optional, default=False): If True the text of the menu selection will be returned instead of the key.
    """
    return_text: bool = False

    def __post_init__(self):
        self.items = [MenuItem(str(i), self.items[i - 1]) for i in range(1, len(self.items) + 1)] + [MenuItem('0', 'Exit')]

    @override
    def show(self) -> str:
        """Show the menu.

        Returns:
            The choice selected from the menu.
        """
        choice = cast(str, super().show())
        return self.items[int(choice) - 1].desc if self.return_text else choice
