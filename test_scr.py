from batcave.sysutil import SysCmdRunner

SysCmdRunner('cmd', 'darg1', dkarg1=True, dkarg2='value').run('arg1', post_option_args=['a'])
