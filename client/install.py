#!/usr/bin/python3
"""
Docloud installer

Usage:
  installer.py install [<install-path>] [-r --reinstall --pkg-path=<path>]
  installer.py package [--pkg-path=<path> --target-x86]
  installer.py package install [<install-path>] [--pkg-path=<path> --target-x86] [-r --reinstall]
  installer.py uninstall

Commands:
  install: Install the package install/ or <install-path>
  package: Create a package in pkg/ or <pkg-path>
  uninstall: Uninstall
  package install: Create a package and install it

Options:
  -h, --help        Show this screen.
  -r, --reinstall   Uninstall before installing
  --pkg-path=<path> Where to put/read package  [default: pkg/]
  --target-x86      Package x86 DLLs instead of x64 DLLs
"""

import sys
if sys.version_info.major < 3:
    sys.stdout.write("USE PYTHON 3!!!!!!!!\n")
    sys.exit()
import os
import sqlite3
from os.path import join, splitext
from shutil import copy, rmtree, copytree

import time
import subprocess
try:
    import winreg
except ImportError:
    winreg = None

# Set in the function main(args) by docopt
ARGS = None

if sys.version_info < (3, 3, 0):
    FileNotFoundError = OSError

script_path = os.path.dirname(os.path.abspath(__file__))

def _spawn(process, *args):
    subprocess.Popen([process] + list(args))

def _get_pkg_path(default=None):
    if ARGS["--pkg-path"] != "pkg/":
        pkg_path = ARGS["--pkg-path"]
    else:
        pkg_path = join(script_path, default if default is not None else "pkg")
    return pkg_path

def package(bits="x64"):
    pkg_path = _get_pkg_path()
    tmppkg_path = os.path.join(pkg_path, "tmppkg")
    print("Creating package at: %s" % pkg_path)
    service_path = join(script_path, "service")
    shared_path = join(script_path, "shared")
    settings_path = join(script_path, "settings")
    docloudext_path = join(script_path, "docloudext")

    try:
        rmtree(pkg_path)
    except FileNotFoundError:
        pass
    os.mkdir(pkg_path)
    os.mkdir(tmppkg_path)
    copy("install.py", pkg_path)
    copy(join(shared_path, "sqlite3", "sqlite3.dll"), tmppkg_path)
    copy(join(shared_path, "schema.sql"), tmppkg_path)

    if bits == "x64":
        dlls = join(shared_path, "libwin64", "gtk3")
    else:
        dlls = join(shared_path, "libwin32", "gtk3")

    print("Bundling %s DLLs" % bits)
    if os.path.exists(dlls) and os.path.isdir(dlls):
        for root, dirs, files in os.walk(dlls):
            for file in files:
                if splitext(file)[1] == ".dll":
                    copy(join(dlls, root, file), join(tmppkg_path, file))

    copy(join(docloudext_path, "docloudext.dll"), tmppkg_path)
    copy(join(service_path, "docloud-svc.exe"), tmppkg_path)

    copy(join(settings_path, "docloud-settings.exe"), tmppkg_path)
    copy(join(settings_path, "main.ui"), tmppkg_path)

    _zipdir(tmppkg_path, os.path.join(pkg_path, "pkg.zip"))
    rmtree(tmppkg_path)
    print("Package created at: %s" % pkg_path)
    return pkg_path

import zipfile
def _zipdir(directory, zip_path):
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for root, dirs, files in os.walk(directory):
            for file in files:
                zipf.write(join(root, file), file)

def _unzip(zip_path, destination):
    with zipfile.ZipFile(zip_path, "r") as zipf:
        zipf.extractall(destination)

def install(pkg_path):
    install_path = ARGS["<install-path>"]
    if not install_path:
        install_path = "install"
    install_path = os.path.abspath(install_path)
    reinstall = ARGS["--reinstall"]

    if reinstall:
        if not uninstall(install_path):
            print("Uninstall failed! Not running re-installation!")
            sys.exit(1)
    print("Installing package from: %s" % pkg_path)
    previous_install_path = _get_registry_install_path()
    if previous_install_path is not None:
        print("Docloud is already installed! No install needed (use -r to reinstall)")
        return
    if os.path.exists(install_path):
        print("Path already exists: %s! No install run (use -r to reinstall)" % install_path)
        return

    _set_registry_install_path(install_path)
    print("Installing in: %s" % install_path)
    tmppkg_path = os.path.join(pkg_path, "tmppkg")
    _unzip(os.path.join(pkg_path, "pkg.zip"), tmppkg_path)

    db_path = join(tmppkg_path, "db.sqlite")
    schema_path = join(tmppkg_path, "schema.sql") \
        if os.path.exists(join(tmppkg_path, "schema.sql")) else join(tmppkg_path, "shared", "schema.sql")

    print("Installing db-schema")
    try:
        conn = sqlite3.connect(db_path)
    except Exception as e:
        print("Could not connect to dababase: %s" % e)
        print("Install stopped")
        return

    try:
        with open(schema_path) as schema_f:
            conn.executescript(schema_f.read())
    except Exception as e:
        print("Could not create schema in db: %s" % e)
        print("Install stopped")
        conn.close()
        return
    conn.close()
    try:
        copytree(tmppkg_path, install_path)
    except OSError as e:
        print("Error copying files: %s" % e)
        print("Install stopped")
        return
    try:
        rmtree(tmppkg_path)
    except OSError as e:
        print("Error removing files: %s" % e)

    print("Loading dll: %s" % join(install_path, "docloudext.dll"))
    os.system("regsvr32 /s %s" % join(install_path, "docloudext.dll"))

    print("Starting service:")
    os.system(join(install_path, "docloud-svc.exe"))

def _get_registry_install_path():
    docloud_key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, "Software\\Docloud\\Docloud")
    try:
        install_path, no = winreg.QueryValueEx(docloud_key, "install_path")
        return install_path
    except FileNotFoundError:
        return None

def _set_registry_install_path(install_path):
    docloud_key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, "Software\\Docloud\\Docloud")
    winreg.SetValueEx(docloud_key, "install_path", 0, winreg.REG_SZ, install_path)

def _delete_registry_keys():
    docloud_key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, "Software\\Docloud\\Docloud")
    winreg.DeleteKey(docloud_key, "")

def uninstall(new_path=None):
    success = True
    print("Uninstalling...")
    install_path = _get_registry_install_path()
    if install_path is not None:
        print("Removing installation at: %s" % install_path)
        docloudext_dll = join(install_path, "docloudext.dll")
        if os.path.exists(docloudext_dll):
            print("Unloading dll %s" % docloudext_dll)
            os.system("regsvr32 /s /u %s" % docloudext_dll)
        os.system("taskkill /f /im explorer.exe")
        os.system("taskkill /f /im docloud-svc.exe")
        time.sleep(0.5)

        if os.path.exists(install_path) and os.path.isdir(install_path):
            try:
                rmtree(install_path)
            except OSError as e:
                print("Error removing files: %s" % e)
                success = False
        _spawn("explorer")
        time.sleep(0.5)
    else:
        print("No installation found!")
    if new_path is not None:
        try:
            rmtree(new_path)
        except FileNotFoundError:
            pass
        except OSError as e:
            print("Error removing files: %s" % e)
            success = False
    _delete_registry_keys()
    return success

def main(args):
    globals()["ARGS"] = args
    if args["uninstall"]:
        uninstall()
    if args["package"]:
        x86 = args["--target-x86"]
        pkg_path = package("x86" if x86 else"x64")
        if args["install"]:
            install(pkg_path)
    elif args["install"]:
        install(_get_pkg_path("."))


#####################################################
# DOCOPT 0.6.1 EMBEDDED BELOW (executes main(args)) #
#####################################################

"""
DOCOPT LICENSE:

Copyright (c) 2012 Vladimir Keleshev, <vladimir@keleshev.com>

Permission is hereby granted, free of charge, to any person
obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software
without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to
whom the Software is furnished to do so, subject to the
following conditions:

The above copyright notice and this permission notice shall
be included in all copies or substantial portions of the
Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY
KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

"""Pythonic command-line interface parser that will make you smile.

 * http://docopt.org
 * Repository and issue-tracker: https://github.com/docopt/docopt
 * Licensed under terms of MIT license (see LICENSE-MIT)
 * Copyright (c) 2013 Vladimir Keleshev, vladimir@keleshev.com

"""
import sys
import re


__all__ = ['docopt']
__version__ = '0.6.1'


class DocoptLanguageError(Exception):

    """Error in construction of usage-message by developer."""


class DocoptExit(SystemExit):

    """Exit in case user invoked program with incorrect arguments."""

    usage = ''

    def __init__(self, message=''):
        SystemExit.__init__(self, (message + '\n' + self.usage).strip())


class Pattern(object):

    def __eq__(self, other):
        return repr(self) == repr(other)

    def __hash__(self):
        return hash(repr(self))

    def fix(self):
        self.fix_identities()
        self.fix_repeating_arguments()
        return self

    def fix_identities(self, uniq=None):
        """Make pattern-tree tips point to same object if they are equal."""
        if not hasattr(self, 'children'):
            return self
        uniq = list(set(self.flat())) if uniq is None else uniq
        for i, c in enumerate(self.children):
            if not hasattr(c, 'children'):
                assert c in uniq
                self.children[i] = uniq[uniq.index(c)]
            else:
                c.fix_identities(uniq)

    def fix_repeating_arguments(self):
        """Fix elements that should accumulate/increment values."""
        either = [list(c.children) for c in self.either.children]
        for case in either:
            for e in [c for c in case if case.count(c) > 1]:
                if type(e) is Argument or type(e) is Option and e.argcount:
                    if e.value is None:
                        e.value = []
                    elif type(e.value) is not list:
                        e.value = e.value.split()
                if type(e) is Command or type(e) is Option and e.argcount == 0:
                    e.value = 0
        return self

    @property
    def either(self):
        """Transform pattern into an equivalent, with only top-level Either."""
        # Currently the pattern will not be equivalent, but more "narrow",
        # although good enough to reason about list arguments.
        ret = []
        groups = [[self]]
        while groups:
            children = groups.pop(0)
            types = [type(c) for c in children]
            if Either in types:
                either = [c for c in children if type(c) is Either][0]
                children.pop(children.index(either))
                for c in either.children:
                    groups.append([c] + children)
            elif Required in types:
                required = [c for c in children if type(c) is Required][0]
                children.pop(children.index(required))
                groups.append(list(required.children) + children)
            elif Optional in types:
                optional = [c for c in children if type(c) is Optional][0]
                children.pop(children.index(optional))
                groups.append(list(optional.children) + children)
            elif AnyOptions in types:
                optional = [c for c in children if type(c) is AnyOptions][0]
                children.pop(children.index(optional))
                groups.append(list(optional.children) + children)
            elif OneOrMore in types:
                oneormore = [c for c in children if type(c) is OneOrMore][0]
                children.pop(children.index(oneormore))
                groups.append(list(oneormore.children) * 2 + children)
            else:
                ret.append(children)
        return Either(*[Required(*e) for e in ret])


class ChildPattern(Pattern):

    def __init__(self, name, value=None):
        self.name = name
        self.value = value

    def __repr__(self):
        return '%s(%r, %r)' % (self.__class__.__name__, self.name, self.value)

    def flat(self, *types):
        return [self] if not types or type(self) in types else []

    def match(self, left, collected=None):
        collected = [] if collected is None else collected
        pos, match = self.single_match(left)
        if match is None:
            return False, left, collected
        left_ = left[:pos] + left[pos + 1:]
        same_name = [a for a in collected if a.name == self.name]
        if type(self.value) in (int, list):
            if type(self.value) is int:
                increment = 1
            else:
                increment = ([match.value] if type(match.value) is str
                             else match.value)
            if not same_name:
                match.value = increment
                return True, left_, collected + [match]
            same_name[0].value += increment
            return True, left_, collected
        return True, left_, collected + [match]


class ParentPattern(Pattern):

    def __init__(self, *children):
        self.children = list(children)

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__,
                           ', '.join(repr(a) for a in self.children))

    def flat(self, *types):
        if type(self) in types:
            return [self]
        return sum([c.flat(*types) for c in self.children], [])


class Argument(ChildPattern):

    def single_match(self, left):
        for n, p in enumerate(left):
            if type(p) is Argument:
                return n, Argument(self.name, p.value)
        return None, None

    @classmethod
    def parse(class_, source):
        name = re.findall('(<\S*?>)', source)[0]
        value = re.findall('\[default: (.*)\]', source, flags=re.I)
        return class_(name, value[0] if value else None)


class Command(Argument):

    def __init__(self, name, value=False):
        self.name = name
        self.value = value

    def single_match(self, left):
        for n, p in enumerate(left):
            if type(p) is Argument:
                if p.value == self.name:
                    return n, Command(self.name, True)
                else:
                    break
        return None, None


class Option(ChildPattern):

    def __init__(self, short=None, long=None, argcount=0, value=False):
        assert argcount in (0, 1)
        self.short, self.long = short, long
        self.argcount, self.value = argcount, value
        self.value = None if value is False and argcount else value

    @classmethod
    def parse(class_, option_description):
        short, long, argcount, value = None, None, 0, False
        options, _, description = option_description.strip().partition('  ')
        options = options.replace(',', ' ').replace('=', ' ')
        for s in options.split():
            if s.startswith('--'):
                long = s
            elif s.startswith('-'):
                short = s
            else:
                argcount = 1
        if argcount:
            matched = re.findall('\[default: (.*)\]', description, flags=re.I)
            value = matched[0] if matched else None
        return class_(short, long, argcount, value)

    def single_match(self, left):
        for n, p in enumerate(left):
            if self.name == p.name:
                return n, p
        return None, None

    @property
    def name(self):
        return self.long or self.short

    def __repr__(self):
        return 'Option(%r, %r, %r, %r)' % (self.short, self.long,
                                           self.argcount, self.value)


class Required(ParentPattern):

    def match(self, left, collected=None):
        collected = [] if collected is None else collected
        l = left
        c = collected
        for p in self.children:
            matched, l, c = p.match(l, c)
            if not matched:
                return False, left, collected
        return True, l, c


class Optional(ParentPattern):

    def match(self, left, collected=None):
        collected = [] if collected is None else collected
        for p in self.children:
            m, left, collected = p.match(left, collected)
        return True, left, collected


class AnyOptions(Optional):

    """Marker/placeholder for [options] shortcut."""


class OneOrMore(ParentPattern):

    def match(self, left, collected=None):
        assert len(self.children) == 1
        collected = [] if collected is None else collected
        l = left
        c = collected
        l_ = None
        matched = True
        times = 0
        while matched:
            # could it be that something didn't match but changed l or c?
            matched, l, c = self.children[0].match(l, c)
            times += 1 if matched else 0
            if l_ == l:
                break
            l_ = l
        if times >= 1:
            return True, l, c
        return False, left, collected


class Either(ParentPattern):

    def match(self, left, collected=None):
        collected = [] if collected is None else collected
        outcomes = []
        for p in self.children:
            matched, _, _ = outcome = p.match(left, collected)
            if matched:
                outcomes.append(outcome)
        if outcomes:
            return min(outcomes, key=lambda outcome: len(outcome[1]))
        return False, left, collected


class TokenStream(list):

    def __init__(self, source, error):
        self += source.split() if hasattr(source, 'split') else source
        self.error = error

    def move(self):
        return self.pop(0) if len(self) else None

    def current(self):
        return self[0] if len(self) else None


def parse_long(tokens, options):
    """long ::= '--' chars [ ( ' ' | '=' ) chars ] ;"""
    long, eq, value = tokens.move().partition('=')
    assert long.startswith('--')
    value = None if eq == value == '' else value
    similar = [o for o in options if o.long == long]
    if tokens.error is DocoptExit and similar == []:  # if no exact match
        similar = [o for o in options if o.long and o.long.startswith(long)]
    if len(similar) > 1:  # might be simply specified ambiguously 2+ times?
        raise tokens.error('%s is not a unique prefix: %s?' %
                           (long, ', '.join(o.long for o in similar)))
    elif len(similar) < 1:
        argcount = 1 if eq == '=' else 0
        o = Option(None, long, argcount)
        options.append(o)
        if tokens.error is DocoptExit:
            o = Option(None, long, argcount, value if argcount else True)
    else:
        o = Option(similar[0].short, similar[0].long,
                   similar[0].argcount, similar[0].value)
        if o.argcount == 0:
            if value is not None:
                raise tokens.error('%s must not have an argument' % o.long)
        else:
            if value is None:
                if tokens.current() is None:
                    raise tokens.error('%s requires argument' % o.long)
                value = tokens.move()
        if tokens.error is DocoptExit:
            o.value = value if value is not None else True
    return [o]


def parse_shorts(tokens, options):
    """shorts ::= '-' ( chars )* [ [ ' ' ] chars ] ;"""
    token = tokens.move()
    assert token.startswith('-') and not token.startswith('--')
    left = token.lstrip('-')
    parsed = []
    while left != '':
        short, left = '-' + left[0], left[1:]
        similar = [o for o in options if o.short == short]
        if len(similar) > 1:
            raise tokens.error('%s is specified ambiguously %d times' %
                               (short, len(similar)))
        elif len(similar) < 1:
            o = Option(short, None, 0)
            options.append(o)
            if tokens.error is DocoptExit:
                o = Option(short, None, 0, True)
        else:  # why copying is necessary here?
            o = Option(short, similar[0].long,
                       similar[0].argcount, similar[0].value)
            value = None
            if o.argcount != 0:
                if left == '':
                    if tokens.current() is None:
                        raise tokens.error('%s requires argument' % short)
                    value = tokens.move()
                else:
                    value = left
                    left = ''
            if tokens.error is DocoptExit:
                o.value = value if value is not None else True
        parsed.append(o)
    return parsed


def parse_pattern(source, options):
    tokens = TokenStream(re.sub(r'([\[\]\(\)\|]|\.\.\.)', r' \1 ', source),
                         DocoptLanguageError)
    result = parse_expr(tokens, options)
    if tokens.current() is not None:
        raise tokens.error('unexpected ending: %r' % ' '.join(tokens))
    return Required(*result)


def parse_expr(tokens, options):
    """expr ::= seq ( '|' seq )* ;"""
    seq = parse_seq(tokens, options)
    if tokens.current() != '|':
        return seq
    result = [Required(*seq)] if len(seq) > 1 else seq
    while tokens.current() == '|':
        tokens.move()
        seq = parse_seq(tokens, options)
        result += [Required(*seq)] if len(seq) > 1 else seq
    return [Either(*result)] if len(result) > 1 else result


def parse_seq(tokens, options):
    """seq ::= ( atom [ '...' ] )* ;"""
    result = []
    while tokens.current() not in [None, ']', ')', '|']:
        atom = parse_atom(tokens, options)
        if tokens.current() == '...':
            atom = [OneOrMore(*atom)]
            tokens.move()
        result += atom
    return result


def parse_atom(tokens, options):
    """atom ::= '(' expr ')' | '[' expr ']' | 'options'
             | long | shorts | argument | command ;
    """
    token = tokens.current()
    result = []
    if token in '([':
        tokens.move()
        matching, pattern = {'(': [')', Required], '[': [']', Optional]}[token]
        result = pattern(*parse_expr(tokens, options))
        if tokens.move() != matching:
            raise tokens.error("unmatched '%s'" % token)
        return [result]
    elif token == 'options':
        tokens.move()
        return [AnyOptions()]
    elif token.startswith('--') and token != '--':
        return parse_long(tokens, options)
    elif token.startswith('-') and token not in ('-', '--'):
        return parse_shorts(tokens, options)
    elif token.startswith('<') and token.endswith('>') or token.isupper():
        return [Argument(tokens.move())]
    else:
        return [Command(tokens.move())]


def parse_argv(tokens, options, options_first=False):
    """Parse command-line argument vector.

    If options_first:
        argv ::= [ long | shorts ]* [ argument ]* [ '--' [ argument ]* ] ;
    else:
        argv ::= [ long | shorts | argument ]* [ '--' [ argument ]* ] ;

    """
    parsed = []
    while tokens.current() is not None:
        if tokens.current() == '--':
            return parsed + [Argument(None, v) for v in tokens]
        elif tokens.current().startswith('--'):
            parsed += parse_long(tokens, options)
        elif tokens.current().startswith('-') and tokens.current() != '-':
            parsed += parse_shorts(tokens, options)
        elif options_first:
            return parsed + [Argument(None, v) for v in tokens]
        else:
            parsed.append(Argument(None, tokens.move()))
    return parsed


def parse_defaults(doc):
    # in python < 2.7 you can't pass flags=re.MULTILINE
    split = re.split('\n *(<\S+?>|-\S+?)', doc)[1:]
    split = [s1 + s2 for s1, s2 in zip(split[::2], split[1::2])]
    options = [Option.parse(s) for s in split if s.startswith('-')]
    #arguments = [Argument.parse(s) for s in split if s.startswith('<')]
    #return options, arguments
    return options


def printable_usage(doc):
    # in python < 2.7 you can't pass flags=re.IGNORECASE
    usage_split = re.split(r'([Uu][Ss][Aa][Gg][Ee]:)', doc)
    if len(usage_split) < 3:
        raise DocoptLanguageError('"usage:" (case-insensitive) not found.')
    if len(usage_split) > 3:
        raise DocoptLanguageError('More than one "usage:" (case-insensitive).')
    return re.split(r'\n\s*\n', ''.join(usage_split[1:]))[0].strip()


def formal_usage(printable_usage):
    pu = printable_usage.split()[1:]  # split and drop "usage:"
    return '( ' + ' '.join(') | (' if s == pu[0] else s for s in pu[1:]) + ' )'


def extras(help, version, options, doc):
    if help and any((o.name in ('-h', '--help')) and o.value for o in options):
        print(doc.strip("\n"))
        sys.exit()
    if version and any(o.name == '--version' and o.value for o in options):
        print(version)
        sys.exit()


class Dict(dict):
    def __repr__(self):
        return '{%s}' % ',\n '.join('%r: %r' % i for i in sorted(self.items()))


def docopt(doc, argv=None, help=True, version=None, options_first=False):
    """Parse `argv` based on command-line interface described in `doc`.

    `docopt` creates your command-line interface based on its
    description that you pass as `doc`. Such description can contain
    --options, <positional-argument>, commands, which could be
    [optional], (required), (mutually | exclusive) or repeated...

    Parameters
    ----------
    doc : str
        Description of your command-line interface.
    argv : list of str, optional
        Argument vector to be parsed. sys.argv[1:] is used if not
        provided.
    help : bool (default: True)
        Set to False to disable automatic help on -h or --help
        options.
    version : any object
        If passed, the object will be printed if --version is in
        `argv`.
    options_first : bool (default: False)
        Set to True to require options preceed positional arguments,
        i.e. to forbid options and positional arguments intermix.

    Returns
    -------
    args : dict
        A dictionary, where keys are names of command-line elements
        such as e.g. "--verbose" and "<path>", and values are the
        parsed values of those elements.

    Example
    -------
    >>> from docopt import docopt
    >>> doc = '''
    Usage:
        my_program tcp <host> <port> [--timeout=<seconds>]
        my_program serial <port> [--baud=<n>] [--timeout=<seconds>]
        my_program (-h | --help | --version)

    Options:
        -h, --help  Show this screen and exit.
        --baud=<n>  Baudrate [default: 9600]
    '''
    >>> argv = ['tcp', '127.0.0.1', '80', '--timeout', '30']
    >>> docopt(doc, argv)
    {'--baud': '9600',
     '--help': False,
     '--timeout': '30',
     '--version': False,
     '<host>': '127.0.0.1',
     '<port>': '80',
     'serial': False,
     'tcp': True}

    See also
    --------
    * For video introduction see http://docopt.org
    * Full documentation is available in README.rst as well as online
      at https://github.com/docopt/docopt#readme

    """
    if argv is None:
        argv = sys.argv[1:]
    DocoptExit.usage = printable_usage(doc)
    options = parse_defaults(doc)
    pattern = parse_pattern(formal_usage(DocoptExit.usage), options)
    # [default] syntax for argument is disabled
    #for a in pattern.flat(Argument):
    #    same_name = [d for d in arguments if d.name == a.name]
    #    if same_name:
    #        a.value = same_name[0].value
    argv = parse_argv(TokenStream(argv, DocoptExit), list(options),
                      options_first)
    pattern_options = set(pattern.flat(Option))
    for ao in pattern.flat(AnyOptions):
        doc_options = parse_defaults(doc)
        ao.children = list(set(doc_options) - pattern_options)
        #if any_options:
        #    ao.children += [Option(o.short, o.long, o.argcount)
        #                    for o in argv if type(o) is Option]
    extras(help, version, argv, doc)
    matched, left, collected = pattern.fix().match(argv)
    if matched and left == []:  # better error message if left?
        return Dict((a.name, a.value) for a in (pattern.flat() + collected))
    raise DocoptExit()


if __name__ == '__main__':
    arguments = docopt(__doc__, version='Docloud 0.1')
    main(arguments)