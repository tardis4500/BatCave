"""This module provides utilities for creating command line menus."""


class MenuItem:
    """Class to represent a single menu item."""

    def __init__(self, key, desc):
        """
        Args:
            key: The key input for the menu selection.
            desc: The text description for the menu selection.

        Attributes:
            desc: The value of the desc argument.
            key: The value of the key argument.
        """
        self.key = key
        self.desc = desc


class Menu:
    """Class to create a universal abstract interface for a command-line menu.

    Attributes:
        _DEFAULT_INVALID_MESSAGE: The default message to use for an invalid choice.
        _DEFAULT_TITLE: The default menu title
        _DEFAULT_PROMPT: The default choice prompt.
    """
    _DEFAULT_INVALID_MESSAGE = '\nInvalid choice\n'
    _DEFAULT_TITLE = '\nSelect one of the following\n'
    _DEFAULT_PROMPT = '-> '

    def __init__(self, items,
                 title=_DEFAULT_TITLE, prompt=_DEFAULT_PROMPT, invalidmsg=_DEFAULT_INVALID_MESSAGE,
                 multiselect=False, ignorecase=True):
        """
        Args:
            items: The list of items for the menu.
            title (optional, default=_DEFAULT_TITLE): The title for the menu.
            prompt (optional, default=_DEFAULT_PROMPT): The prompt for the menu.
            invalidmsg (optional, default=_DEFAULT_INVALID_MESSAGE): The invalid choice message.
            multiselect (optional, default=False): If True, multiple options can be selected.
            ignorecase (optional, default=True): If True, menu input will be case insensitive.

        Attributes:
            ignorecase: The value of the ignorecase argument.
            invalidmsg: The value of the invalidmsg argument.
            items: The value of the items argument.
            multiselect: The value of the multiselect argument.
            prompt: The value of the prompt argument.
            title: The value of the title argument.
        """
        self.items = items
        self.title = title
        self.prompt = prompt
        self.invalidmsg = invalidmsg
        self.multiselect = multiselect
        self.ignorecase = ignorecase

    def show(self):
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


class SimpleMenu(Menu):
    """A simplified version of the Menu class."""

    def __init__(self, itemlist, return_text=False, **args):
        """
        Args:
            itemlist: The list of items for the menu to which an 'Exit' option will be appended.
            return_text (optional, default=False): If True the text of the menu selection will be returned instead of the key.
            args (optional): A dictionary of arguments to pass to the base Menu class.

        Attributes:
            itemlist: The value of the itemlist argument with ['Exit'] appended.
            return_text: The value of the return_text argument.
        """
        self.itemlist = list(itemlist) + ['Exit']
        self.return_text = return_text
        super().__init__([MenuItem(str(i), itemlist[i-1]) for i in range(1, len(itemlist)+1)] + [MenuItem('0', 'Exit')], **args)

    def show(self):
        """Show the menu.

        Returns:
            The choice selected from the menu.
        """
        choice = super().show()
        return self.itemlist[int(choice) - 1] if self.return_text else choice
