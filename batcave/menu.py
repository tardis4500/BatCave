"""This module provides utilities for creating command line menus."""

# Import standard modules
from dataclasses import dataclass
from typing import cast, List, Union


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
            invalidmsg (optional, default=_DEFAULT_INVALID_MESSAGE): The invalid choice message.
            multiselect (optional, default=False): If True, multiple options can be selected.
            ignorecase (optional, default=True): If True, menu input will be case insensitive.
    """
    items: List[MenuItem]
    title: str = '\nSelect one of the following\n'
    prompt: str = '-> '
    invalidmsg: str = '\nInvalid choice\n'
    multiselect: bool = False
    ignorecase: bool = True

    def show(self) -> Union[str, List[str]]:
        """Show the menu.

        Returns:
            The choice selected from the menu.
        """
        invalid_choice = True
        valid_choices = list()
        menu = self.title + '\n'
        for item in self.items:
            valid_choices.append(item.key.upper() if self.ignorecase else item.key)
            menu += f'\t{item.key}. {item.desc}\n'

        choices = list()
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
                print(self.invalidmsg)
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
        itemlist = list(self.itemlist) + ['Exit']  # pylint: disable=access-member-before-definition
        self.itemlist = [MenuItem(str(i), itemlist[i - 1]) for i in range(1, len(itemlist) + 1)] + [MenuItem('0', 'Exit')]

    def show(self) -> str:
        """Show the menu.

        Returns:
            The choice selected from the menu.
        """
        choice = cast(str, super().show())
        return self.itemlist[int(choice) - 1] if self.return_text else choice
