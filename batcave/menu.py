'Creates a simple command line menu'


class MenuItem:
    'A item in the menu'
    def __init__(self, key, desc):
        self.key = key
        self.desc = desc


class Menu:
    'A simple menu processor'
    _DEFAULT_INVALID_MESSAGE = '\nInvalid choice\n'
    _DEFAULT_TITLE = '\nSelect one of the following\n'
    _DEFAULT_PROMPT = '-> '

    def __init__(self, items,
                 title=_DEFAULT_TITLE, prompt=_DEFAULT_PROMPT, invalidmsg=_DEFAULT_INVALID_MESSAGE,
                 multiselect=False, ignorecase=True):
        self.items = items
        self.title = title
        self.prompt = prompt
        self.invalidmsg = invalidmsg
        self.multiselect = multiselect
        self.ignorecase = ignorecase

    def show(self):
        'Show the menu'
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
    'A simplified menu'
    def __init__(self, itemlist, return_text=False, **args):
        self.itemlist = list(itemlist) + ['Exit']
        self.return_text = return_text
        super().__init__([MenuItem(str(i), itemlist[i-1]) for i in range(1, len(itemlist)+1)] + [MenuItem('0', 'Exit')], **args)

    def show(self):
        choice = super().show()
        return self.itemlist[int(choice) - 1] if self.return_text else choice
