#!/usr/bin/env python

import argparse
import sys
import re
import subprocess
import os
import contextlib
import shutil
import stat
from collections import *
from itertools import *


# Default paths to Mercurial and Git
hg_cmd = 'hg'
git_cmd = 'git'
ver = '0.1.2'

ignores = [
    # Version control folders
    ".hg",
    ".git",
    ".svn",
    ".CVS",
    ".cvs",
    
    # Version control fallout
    "*.orig",
    
    # mbed Tools
    ".build",
    ".export",
    
    # Online IDE caches
    ".msub",
    ".meta",
    ".ctags*",
    
    # uVision project files
    "*.uvproj",
    "*.uvopt",
    
    # Eclipse project files
    "*.project",
    "*.cproject",
    "*.launch",
    
    # IAR project files
    "*.ewp",
    "*.eww",
    
    # GCC make
    "Makefile",
    "Debug",
    
    # HTML files
    "*.htm",
    
    # Settings files
    "*.settings",
    "mbed_settings.py",
    
    # Python 
    "*.py[cod]",
    "# subrepo ignores",
    ]

# reference to local (unpublished) repo - dir#rev
regex_local_ref = '^([\w.+-][\w./+-]*?)/?(?:#(.*))?$'

# reference to repo - url#rev
regex_url_ref = '^(.*/([\w+-]+)(?:\.\w+)?)/?(?:#(.*))?$'

# git url (no #rev)
regex_git_url = '^(git@|git\://|ssh\://|https?\://)([^/:]+)[:/](.+?)(\.git|\/?)$'

# hg url (no #rev)
regex_hg_url = '^(file|ssh|https?)://([^/:]+)/([^/]+)/?([^/]+?)?$'

# mbed url is subset of hg. mbed doesn't support ssh transport
regex_mbed_url = '^(https?)://([\w\-\.]*mbed\.(co\.uk|org|com))/(users|teams)/([\w\-]{1,32})/(repos|code)/([\w\-]+)/?$'

# default mbed OS url
mbed_os_url = 'https://github.com/ARMmbed/mbed-os'

# verbose logging
verbose = False


# Logging and output
def message(msg):
    return "[mbed] %s\n" % msg

def log(msg, level=1):
    if level <= 0 or verbose:
        sys.stderr.write(message(msg))
    
def action(msg):
    sys.stderr.write(message(msg))

def warning(msg):
    for line in msg.splitlines():
        sys.stderr.write("[mbed WARNING] %s\n" % line)
    sys.stderr.write("---\n")

def error(msg, code=-1):
    for line in msg.splitlines():
        sys.stderr.write("[mbed ERROR] %s\n" % line)
    sys.stderr.write("---\n")
    sys.exit(code)

def progress_cursor():
    while True:
        for cursor in '|/-\\':
            yield cursor

progress_spinner = progress_cursor()

def progress():
    sys.stdout.write(progress_spinner.next())
    sys.stdout.flush()
    sys.stdout.write('\b')


# Process execution
class ProcessException(Exception):
    pass

def popen(command, stdin=None, **kwargs):
    # print for debugging
    log('"'+' '.join(command)+'"')
    proc = subprocess.Popen(command, **kwargs)

    if proc.wait() != 0:
        raise ProcessException(proc.returncode)

def pquery(command, stdin=None, **kwargs):
    #log("Query "+' '.join(command)+" in "+os.getcwd())
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
    stdout, _ = proc.communicate(stdin)

    if proc.returncode != 0:
        raise ProcessException(proc.returncode)

    return stdout

def rmtree_readonly(directory):
    def remove_readonly(func, path, _):
        os.chmod(path, stat.S_IWRITE)
        func(path)

    shutil.rmtree(directory, onerror=remove_readonly)


# Defaults config file
def set_cfg(file, var, val):
    try:
        with open(file) as f:
            lines = f.read().splitlines()
    except:
        lines = []

    for line in lines:
        m = re.match('^([\w+-]+)\=(.*)?$', line)
        if m and m.group(1) == var:
            lines.remove(line)

    lines += [var+"="+val]

    with open(file, 'w') as f:
        f.write('\n'.join(lines) + '\n')

def get_cfg(file, var, default_val=None):
    try:
        with open(file) as f:
            lines = f.read().splitlines()
    except:
        lines = []

    for line in lines:
        m = re.match('^([\w+-]+)\=(.*)?$', line)
        if m and m.group(1) == var:
            return m.group(2)
    return default_val


# Directory navigation
@contextlib.contextmanager
def cd(newdir):
    prevdir = os.getcwd()
    os.chdir(newdir)
    try:
        yield
    finally:
        os.chdir(prevdir)

def relpath(root, path):
    return path[len(root)+1:]


def staticclass(cls):
    for k, v in cls.__dict__.items():
        if hasattr(v, '__call__') and not k.startswith('__'):
            setattr(cls, k, staticmethod(v))

    return cls


# Handling for multiple version controls
scms = {}
def scm(name):
    def scm(cls):
        scms[name] = cls()
        return cls
    return scm

# pylint: disable=no-self-argument
# pylint: disable=no-method-argument
# pylint: disable=no-member
@scm('hg')
@staticclass
class Hg(object):
    name = 'hg'
    store = '.hg'

    def isurl(url):
        m_url = re.match(regex_url_ref, url.strip().replace('\\', '/'))
        if m_url:
            return re.match(regex_hg_url, m_url.group(1)) or re.match(regex_mbed_url, m_url.group(1))
        else:
            return False

    def init(path=None):
        popen([hg_cmd, 'init'] + ([path] if path else []) + (['-v'] if verbose else ['-q']))

    def clone(url, name=None, hash=None, depth=None, protocol=None):
        popen([hg_cmd, 'clone', formaturl(url, protocol), name] + (['-v'] if verbose else ['-q']))
        if hash:
            with cd(name):
                try:
                    popen([hg_cmd, 'checkout', hash] + (['-v'] if verbose else ['-q']))
                except ProcessException:
                    error("Unable to update to revision \"%s\"" % hash, 1)

    def add(file):
        log("Adding reference \"%s\"" % file)
        try:
            popen([hg_cmd, 'add', file] + (['-v'] if verbose else ['-q']))
        except ProcessException:
            pass
        
    def remove(file):
        log("Removing reference \"%s\" " % file)
        try:
            popen([hg_cmd, 'rm', '-f', file] + (['-v'] if verbose else ['-q']))
        except ProcessException:
            pass
        try:
            os.remove(file)
        except OSError:
            pass

    def commit():
        popen([hg_cmd, 'commit'] + (['-v'] if verbose else ['-q']))
        
    def push(repo, all=None):
        popen([hg_cmd, 'push'] + (['--new-branch'] if all else []) + (['-v'] if verbose else ['-q']))
        
    def pull(repo):
        popen([hg_cmd, 'pull'] + (['-v'] if verbose else ['-q']))

    def update(repo, hash=None, clean=False):
        log("Pulling remote repository \"%s\" to local \"%s\"" % (repo.url, repo.name))
        popen([hg_cmd, 'pull'] + (['-v'] if verbose else ['-q']))
        log("Updating \"%s\" to %s" % (repo.name, "rev #"+hash if hash else "latest revision in the current branch"))
        popen([hg_cmd, 'update'] + (['-r', hash] if hash else []) + (['-C'] if clean else []) + (['-v'] if verbose else ['-q']))

    def status():
        return pquery([hg_cmd, 'status'] + (['-v'] if verbose else ['-q']))

    def dirty():
        return pquery([hg_cmd, 'status', '-q'])

    def untracked():
        result = pquery([hg_cmd, 'status', '-u'])
        return re.sub('^\? ', '', result).splitlines()

    def outgoing():
        try:
            pquery([hg_cmd, 'outgoing'])
            return True
        except ProcessException as e:
            if e[0] != 1:
                raise
            return False

    def isdetached():
        return False

    def geturl(repo):
        tagpaths = '[paths]'
        default_url = ''
        url = ''
        if os.path.isfile(os.path.join(repo.path, '.hg/hgrc')):
            with open(os.path.join(repo.path, '.hg/hgrc')) as f: 
                lines = f.read().splitlines()
                if tagpaths in lines:
                    idx = lines.index(tagpaths)
                    m = re.match('^([\w_]+)\s*=\s*(.*)?$', lines[idx+1])
                    if m:
                        if m.group(1) == 'default':
                            default_url = m.group(2)
                        else:
                            url = m.group(2)
            if default_url:
                url = default_url

        return formaturl(url or pquery([hg_cmd, 'paths', 'default']).strip())

    def gethash(repo):
        if os.path.isfile(os.path.join(repo.path, '.hg', 'dirstate')):
            with open(os.path.join(repo.path, '.hg', 'dirstate'), 'rb') as f:
                return ''.join('%02x'%ord(i) for i in f.read(6))
        else:
            return ""
            
    def ignores(repo):
        hook = 'ignore.local = .hg/hgignore'
        hgrc = os.path.join(repo.path, '.hg', 'hgrc')
        try: 
            with open(hgrc) as f:
                exists = hook in f.read().splitlines()
        except IOError:
            exists = False
            
        if not exists:
            try:
                with open(hgrc, 'a') as f:
                    f.write('[ui]\n')
                    f.write(hook + '\n')
            except IOError:
                error("Unable to write hgrc file in \"%s\"" % hgrc, 1)

        exclude = os.path.join(repo.path, '.hg', 'hgignore')
        try:
            with open(exclude, 'w') as f:
                f.write("syntax: glob\n"+'\n'.join(ignores)+'\n')
        except IOError:
            error("Unable to write ignore file in \"%s\"" % exclude, 1)

    def ignore(repo, file):
        hook = 'ignore.local = .hg/hgignore'
        hgrc = os.path.join(repo.path, '.hg', 'hgrc')
        try: 
            with open(hgrc) as f:
                exists = hook in f.read().splitlines()
        except IOError:
            exists = False

        if not exists:
            try:
                with open(hgrc, 'a') as f:
                    f.write('[ui]\n')
                    f.write(hook + '\n')
            except IOError:
                error("Unable to write hgrc file in \"%s\"" % hgrc, 1)

        exclude = os.path.join(repo.path, '.hg/hgignore')
        try: 
            with open(exclude) as f:
                exists = file in f.read().splitlines()
        except IOError:
            exists = False

        if not exists:
            try:
                with open(exclude, 'a') as f:
                    f.write(file + '\n')
            except IOError:
                error("Unable to write ignore file in \"%s\"" % exclude, 1)

    def unignore(repo, file):
        exclude = os.path.join(repo.path, '.hg', 'hgignore')
        try:
            with open(exclude) as f:
                lines = f.read().splitlines()
        except:
            lines = []

        if file not in lines:
            return

        lines.remove(file)

        try:
            with open(exclude, 'w') as f:
                f.write('\n'.join(lines) + '\n')
        except IOError:
            error("Unable to write ignore file in \"%s\"" % exclude, 1)
            
# pylint: disable=no-self-argument
# pylint: disable=no-method-argument
# pylint: disable=no-member
@scm('git')
@staticclass
class Git(object):
    name = 'git'
    store = '.git'

    def isurl(url):
        m_url = re.match(regex_url_ref, url.strip().replace('\\', '/'))
        if m_url:
            return re.match(regex_git_url, m_url.group(1)) and not re.match(regex_mbed_url, m_url.group(1))
        else:
            return False

    def init(path=None):
        popen([git_cmd, 'init'] + ([path] if path else []) + ([] if verbose else ['-q']))

    def clone(url, name=None, hash=None, depth=None, protocol=None):
        popen([git_cmd, 'clone', formaturl(url, protocol), name] + (['--depth', depth] if depth else []) + (['-v'] if verbose else ['-q']))
        if hash:
            with cd(name):
                try:
                    popen([git_cmd, 'checkout', '-q', hash] + ([] if verbose else ['-q']))
                except ProcessException:
                    error("Unable to update to revision \"%s\"" % hash, 1)

    def add(file):
        log("Adding reference "+file)
        try:
            popen([git_cmd, 'add', file] + (['-v'] if verbose else []))
        except ProcessException:
            pass
        
    def remove(file):
        log("Removing reference "+file)
        try:
            popen([git_cmd, 'rm', '-f', file] + ([] if verbose else ['-q']))
        except ProcessException:
            pass
        try:
            os.remove(file)
        except OSError:
            pass

    def commit():
        popen([git_cmd, 'commit', '-a'] + (['-v'] if verbose else ['-q']))
        
    def push(repo, all=None):
        popen([git_cmd, 'push'] + (['--all'] if all else []) + (['-v'] if verbose else ['-q']))
        
    def pull(repo):
        popen([git_cmd, 'fetch', '--all'] + (['-v'] if verbose else ['-q']))

    def update(repo, hash=None, clean=False):
        if clean:
            log("Discarding local changes in \"%s\"" % repo.name)
            popen([git_cmd, 'reset', 'HEAD'] + ([] if verbose else ['-q'])) # unmarks files for commit
            popen([git_cmd, 'checkout', '.'] + ([] if verbose else ['-q'])) # undo  modified files
            popen([git_cmd, 'clean', '-fdq'] + ([] if verbose else ['-q'])) # cleans up untracked files and folders
        if hash:
            log("Fetching remote repository \"%s\" to local \"%s\"" % (repo.url, repo.name))
            popen([git_cmd, 'fetch', '-v', '--all'] + (['-v'] if verbose else ['-q']))
            log("Updating \"%s\" to rev #%s" % (repo.name, hash))
            popen([git_cmd, 'checkout'] + [hash] + ([] if verbose else ['-q']))
        else:
            log("Fetching remote repository \"%s\" to local \"%s\" and updating to latest revision in the current branch" % (repo.url, repo.name))
            popen([git_cmd, 'pull', '--all'] + (['-v'] if verbose else ['-q']))

    def status():
        return pquery([git_cmd, 'status', '-s'] + (['-v'] if verbose else []))
        
    def dirty():
        return pquery([git_cmd, 'diff', '--name-only', 'HEAD'])

    def untracked():
        return pquery([git_cmd, 'ls-files', '--others', '--exclude-standard']).splitlines()

    def outgoing():
        try:
            return True if pquery([git_cmd, 'log', 'origin..']) else False
        except ProcessException as e:
            if e[0] != 1:
                raise
            return True

    def isdetached():
        branch = pquery([git_cmd, 'rev-parse', '--symbolic-full-name', '--abbrev-ref', 'HEAD']).strip()
        return branch == "HEAD"

    def geturl(repo):
        url = ""
        remotes = pquery([git_cmd, 'remote', '-v']).strip().splitlines()
        for remote in remotes:
            remote = re.split("\s", remote)
            if "(fetch)" in remote:
                url = remote[1]
                if remote[0] == "origin": # Prefer origin URL
                    break
        return formaturl(url)

    def gethash(repo):
        return pquery([git_cmd, 'rev-parse', 'HEAD']).strip()

    def ignores(repo):
        with open(os.path.join(repo.path, '.git/info/exclude'), 'w') as f:
            f.write('\n'.join(ignores)+'\n')

    def ignore(repo, file):
        exclude = os.path.join(repo.path, '.git/info/exclude')
        try: 
            with open(exclude) as f:
                exists = file in f.read().splitlines()
        except IOError:
            exists = False

        if not exists:
            with open(exclude, 'a') as f:
                f.write(file.replace("\\", "/") + '\n')

    def unignore(repo, file):
        exclude = os.path.join(repo.path, '.git/info/exclude')
        try:
            with open(exclude) as f:
                lines = f.read().splitlines()
        except:
            lines = []

        if file not in lines:
            return

        lines.remove(file)

        with open(exclude, 'w') as f:
            f.write('\n'.join(lines) + '\n')


# Repository object
class Repo(object):
    is_local = False
    
    @classmethod
    def fromurl(cls, url, path=None):
        repo = cls()
        m_local = re.match(regex_local_ref, url.strip().replace('\\', '/'))
        m_url = re.match(regex_url_ref, url.strip().replace('\\', '/'))
        if m_local:
            repo.name = os.path.basename(path or m_local.group(1))
            repo.path = os.path.abspath(path or os.path.join(os.getcwd(), m_local.group(1)))
            repo.url = m_local.group(1)
            repo.hash = m_local.group(2)
            repo.is_local = True
        elif m_url:
            repo.name = os.path.basename(path or m_url.group(2))
            repo.path = os.path.abspath(path or os.path.join(os.getcwd(), repo.name))
            repo.url = formaturl(m_url.group(1))
            repo.hash = m_url.group(3)
        else:
            error('Invalid repository (%s)' % url.strip(), -1)
        return repo

    @classmethod
    def fromlib(cls, lib=None):
        assert lib.endswith('.lib')
        with open(lib) as f:
            return cls.fromurl(f.read(), lib[:-4])

    @classmethod
    def fromrepo(cls, path=None):
        repo = cls()
        if path is None:
            path = Repo.findrepo(os.getcwd())
            if path is None:
                error('Cannot find the program or library in the current path \"%s\".\nPlease change your working directory to a different location or use command \"new\" to create a new program.' % os.getcwd(), 1)

        repo.path = os.path.abspath(path)
        repo.name = os.path.basename(repo.path)

        repo.sync()

        if repo.scm is None:
            error("Current folder is not a supported repository", -1)

        return repo

    @classmethod
    def isrepo(cls, path=None):
        for name, scm in scms.items():
            if os.path.isdir(os.path.join(path, '.'+name)):
               return True
        else:
            return False
            
        return False

    @classmethod
    def findrepo(cls, path=None):
        path = os.path.abspath(path or os.getcwd())

        while cd(path):
            if Repo.isrepo(path):
                return path

            tpath = path
            path = os.path.split(path)[0]
            if tpath == path:
                break

        return None

    @classmethod
    def findroot(cls, path=None):
        path = os.path.abspath(path or os.getcwd())
        rpath = None

        while cd(path):
            tpath = path
            path = Repo.findrepo(path)
            if path:
                rpath = path
                path = os.path.split(path)[0]
                if tpath == path:       # Reached root.
                    break
            else:
                break

        return rpath

    @classmethod
    def typerepo(cls, path=None):
        path = os.path.abspath(path or os.getcwd())

        depth = 0
        while cd(path):
            tpath = path
            path = Repo.findrepo(path)
            if path:
                depth += 1
                path = os.path.split(path)[0]
                if tpath == path:       # Reached root.
                    break
            else:
                break

        return "directory" if depth == 0 else ("program" if depth == 1 else "library")

    @property
    def lib(self):
        return self.path + '.lib'

    @property
    def fullurl(self):
        if self.url:
            return (self.url.rstrip('/') + '/' +
                ('#'+self.hash if self.hash else ''))

    def sync(self):
        self.url = None
        self.hash = None
        if os.path.isdir(self.path):
            try:
                self.scm = self.getscm()
            except ProcessException:
                pass

            try:
                self.url = self.geturl()
                if not self.url:
                    self.is_local = True
                    ppath = self.findrepo(os.path.split(self.path)[0])
                    self.url = relpath(ppath, self.path).replace("\\", "/") if ppath else os.path.basename(self.path)
            except ProcessException:
                pass

            try:
                self.hash = self.gethash()
            except ProcessException:
                pass

            try:
                self.libs = list(self.getlibs())
            except ProcessException:
                pass

    def getscm(self):
        for name, scm in scms.items():
            if os.path.isdir(os.path.join(self.path, '.'+name)):
                return scm

    def gethash(self):
        if self.scm:
            with cd(self.path):
                return self.scm.gethash(self)

    def geturl(self):
        if self.scm:
            with cd(self.path):
                return self.scm.geturl(self).strip().replace('\\', '/')

    def getlibs(self):
        for root, dirs, files in os.walk(self.path):
            dirs[:]  = [d for d in dirs  if not d.startswith('.')]
            files[:] = [f for f in files if not f.startswith('.')]

            for file in files:
                if file.endswith('.lib'):
                    yield Repo.fromlib(os.path.join(root, file))
                    if file[:-4] in dirs:
                        dirs.remove(file[:-4])

    def write(self):
        if os.path.isfile(self.lib):
            with open(self.lib) as f:
                lib_repo = Repo.fromurl(f.read().strip())
                if (formaturl(lib_repo.url, 'https') == formaturl(self.url, 'https') # match URLs in common format (https)
                    and (lib_repo.hash == self.hash                                  # match hashes, even if hash is None (valid for repos with no revisions)
                    or lib_repo.hash == self.hash[0:len(lib_repo.hash)])):           # match long and short hash formats
                    #print self.name, 'unmodified'
                    progress()
                    return

        action("Updating reference \"%s\" -> \"%s\"" % (relpath(cwd_root, self.path) if cwd_root != self.path else self.name, self.fullurl))
        
        with open(self.lib, 'wb') as f:
            f.write(self.fullurl + '\n')

    def rm_untracked(self):
        untracked = self.scm.untracked()
        for file in untracked:
            if re.match("(.+)\.lib$", file) and os.path.isfile(file):
                action("Remove untracked library reference \"%s\"" % file)
                os.remove(file)

    def can_update(self, clean, force):
        if (self.is_local or self.url is None) and not force:
            return False, "Preserving local library \"%s\" in \"%s\".\nPlease publish this library to a remote URL to be able to restore it at any time.\nYou can use --ignore switch to ignore all local libraries and update only the published ones.\nYou can also use --force switch to remove all local libraries. WARNING: This action cannot be undone." % (self.name, self.path)
        if not clean and self.scm.dirty():
            return False, "Uncommitted changes in \"%s\" in \"%s\".\nPlease discard or stash them first and then retry update.\nYou can also use --clean switch to discard all uncommitted changes. WARNING: This action cannot be undone." % (self.name, self.path)
        if not force and self.scm.outgoing():
            return False, "Unpublished changes in \"%s\" in \"%s\".\nPlease publish them first using the \"publish\" command.\nYou can also use --force to discard all local commits and replace the library with the one included in this revision. WARNING: This action cannot be undone." % (self.name, self.path)

        return True, "OK"

    def check_repo(self, show_warning=None):
        if not os.path.isdir(self.path):
            if show_warning:
                warning("Library reference \"%s\" points to non-existing library in \"%s\"\nYou can use \"deploy\" command to import the missing libraries.\nYou can also use \"sync\" command to synchronize and remove all invalid library references." % (os.path.basename(self.lib), self.path))
            else:
                error("Library reference \"%s\" points to non-existing library in \"%s\"\nYou can use \"deploy\" command to import the missing libraries\nYou can also use \"sync\" command to synchronize and remove all invalid library references." % (os.path.basename(self.lib), self.path), 1)
            return False
        elif not self.isrepo(self.path):
            if show_warning:
                warning("Library reference \"%s\" points to a folder \"%s\", which is not a valid repository.\nYou can remove the conflicting folder manually and use \"deploy\" command to import the missing libraries\nYou can also remove library reference \"%s\" and use the \"sync\" command again." % (os.path.basename(self.lib), self.path, self.lib))
            else:
                error("Library reference \"%s\" points to a folder \"%s\", which is not a valid repository.\nYou can remove the conflicting folder manually and use \"deploy\" command to import the missing libraries\nYou can also remove library reference \"%s\" and use the \"sync\" command again." % (os.path.basename(self.lib), self.path, self.lib), 1)
            return False

        return True

                
def formaturl(url, format="default"):
    url = "%s" % url
    m = re.match(regex_mbed_url, url)
    if m:
        if format == "http":
            url = 'http://%s/%s/%s/%s/%s' % (m.group(2), m.group(4), m.group(5), m.group(6), m.group(7))
        else:
            url = 'https://%s/%s/%s/%s/%s' % (m.group(2), m.group(4), m.group(5), m.group(6), m.group(7))
    else:
        m = re.match(regex_git_url, url)
        if m:
            if format == "ssh":
                url = 'ssh://%s/%s.git' % (m.group(2), m.group(3))
            elif format == "http":
                url = 'http://%s/%s' % (m.group(2), m.group(3))
            else:
                url = 'https://%s/%s' % (m.group(2), m.group(3)) # https is default
        else:
            m = re.match(regex_hg_url, url)
            if m:
                if format == "ssh":
                    url = 'ssh://%s/%s' % (m.group(2), m.group(3))
                elif format == "http":
                    url = 'http://%s/%s' % (m.group(2), m.group(3))
                else:
                    url = 'https://%s/%s' % (m.group(2), m.group(3)) # https is default
    return url



# Help messages adapt based on current dir
cwd_type = Repo.typerepo()
cwd_dest = "program" if cwd_type == "directory" else "library"
cwd_root = os.getcwd()

# Subparser handling
parser = argparse.ArgumentParser(description="Command-line code management tool for ARM mbed OS - http://www.mbed.com\nversion %s" % ver)
subparsers = parser.add_subparsers(title="Commands", metavar="           ")

# Process handling
def subcommand(name, *args, **kwargs):
    def subcommand(command):
        subparser = subparsers.add_parser(name, **kwargs)
    
        for arg in args:
            arg = dict(arg)
            opt = arg['name']
            del arg['name']

            if isinstance(opt, basestring):
                subparser.add_argument(opt, **arg)
            else:
                subparser.add_argument(*opt, **arg)

        subparser.add_argument("-v", "--verbose", action="store_true", dest="verbose", help="Verbose diagnostic output")
    
        def thunk(parsed_args):
            argv = [arg['dest'] if 'dest' in arg else arg['name'] for arg in args]
            argv = [(arg if isinstance(arg, basestring) else arg[-1]).strip('-')
                    for arg in argv]
            argv = {arg: vars(parsed_args)[arg] for arg in argv
                    if vars(parsed_args)[arg]}

            return command(**argv)
    
        subparser.set_defaults(command=thunk)
        return command
    return subcommand


# Clone command
@subcommand('new', 
    dict(name='name', help='Destination name or path'),
    dict(name='scm', nargs='?', help='Source control management. Currently supported: %s. Default: git' % ', '.join([s.name for s in scms.values()])),
    dict(name='--depth', nargs='?', help='Number of revisions to fetch the mbed-os repository when creating new program. Default: all revisions.'),
    dict(name='--protocol', nargs='?', help='Transport protocol when fetching the mbed-os repository when creating new program. Supported: https, http, ssh, git. Default: inferred from URL.'),
    help='Create a new program based on the specified source control management. Will create a new library when called from inside a local program. Supported SCMs: %s.' % (', '.join([s.name for s in scms.values()])))
def new(name, scm='git', depth=None, protocol=None):
    global cwd_root
    
    d_path = name or os.getcwd()
    if os.path.isdir(d_path):
        if Repo.isrepo(d_path):
            error("A %s is already exists in \"%s\". Please select a different name or location." % (cwd_dest, d_path), 1)
        if len(os.listdir(d_path)) > 1:
            warning("Directory \"%s\" is not empty." % d_path)

    p_path = Repo.findrepo(d_path)  # Find parent repository before the new one is created

    repo_scm = [s for s in scms.values() if s.name == scm.lower()]
    if not repo_scm:
        error("Please specify one of the following source control management systems: %s" % ', '.join([s.name for s in scms.values()]), 1)

    action("Creating new %s \"%s\" (%s)" % (cwd_dest, os.path.basename(d_path), repo_scm[0].name))
    repo_scm[0].init(d_path)        # Initialize repository

    if p_path:  # It's a library
        with cd(p_path):
            sync()
    else:       # It's a program. Add mbed-os
        # This helps sub-commands to display relative paths to the created program
        cwd_root = os.path.abspath(d_path)
        
        try:
            with cd(d_path):
                add(mbed_os_url, depth=depth, protocol=protocol)
        except:
            rmtree_readonly(d_path)
            raise
        if d_path:
            os.chdir(d_path)


# Clone command
@subcommand('import', 
    dict(name='url', help='URL of the %s' % cwd_dest),
    dict(name='path', nargs='?', help='Destination name or path. Default: current %s.' % cwd_type),
    dict(name='--depth', nargs='?', help='Number of revisions to fetch from the remote repository. Default: all revisions.'),
    dict(name='--protocol', nargs='?', help='Transport protocol for the source control management. Supported: https, http, ssh, git. Default: inferred from URL.'),
    help='Import a program and its dependencies into the current directory or specified destination path.')
def import_(url, path=None, depth=None, protocol=None, top=True):
    global cwd_root
    
    repo = Repo.fromurl(url, path)
    if top and cwd_type != "directory":
            error("Cannot import program in the specified location \"%s\" because it's already part of a program.\nPlease change your working directory to a different location or use command \"add\" to import the URL as a library." % os.path.abspath(repo.path), 1)

    if os.path.isdir(repo.path) and len(os.listdir(repo.path)) > 1:
        error("Directory \"%s\" is not empty. Please ensure that the destination folder is empty." % repo.path, 1)

    # Sorted so repositories that match urls are attempted first
    sorted_scms = [(scm.isurl(url), scm) for scm in scms.values()]
    sorted_scms = sorted(sorted_scms, key=lambda (m, _): not m)

    text = "Importing program" if top else "Adding library"
    action("%s \"%s\" from \"%s/\"%s" % (text, relpath(cwd_root, repo.path), repo.url, ' at rev #'+repo.hash if repo.hash else ''))
    for _, scm in sorted_scms:
        try:
            scm.clone(repo.url, repo.path, repo.hash, depth=depth, protocol=protocol)
            break
        except ProcessException:
            if os.path.isdir(repo.path):
                rmtree_readonly(repo.path)
            pass
    else:
        error("Unable to clone repository (%s)" % url, 1)

    repo.sync()

    if top: # This helps sub-commands to display relative paths to the imported program
        cwd_root = repo.path

    with cd(repo.path):
        deploy(depth=depth, protocol=protocol)

# Deploy command
@subcommand('deploy',
    dict(name='--depth', nargs='?', help='Number of revisions to fetch from the remote repository. Default: all revisions.'),
    dict(name='--protocol', nargs='?', help='Transport protocol for the source control management. Supported: https, http, ssh, git. Default: inferred from URL.'),
    help="Import missing dependencies in the current program or library.")
def deploy(depth=None, protocol=None):
    repo = Repo.fromrepo()
    repo.scm.ignores(repo)

    for lib in repo.libs:
        if os.path.isdir(lib.path):
            if lib.check_repo():
                with cd(lib.path):
                    update(lib.hash, depth=depth, protocol=protocol, top=False)
        else:
            import_(lib.fullurl, lib.path, depth=depth, protocol=protocol, top=False)
            repo.scm.ignore(repo, relpath(repo.path, lib.path))

    # This has to be replaced by one time python script from tools that sets up everything the developer needs to use the tools
    if (not os.path.isfile('mbed_settings.py') and 
        os.path.isfile('mbed-os/tools/default_settings.py')):
        shutil.copy('mbed-os/tools/default_settings.py', 'mbed_settings.py')


# Install/uninstall command
@subcommand('add', 
    dict(name='url', help="URL of the library"),
    dict(name='path', nargs='?', help="Destination name or path. Default: current folder."),
    dict(name='--depth', nargs='?', help='Number of revisions to fetch from the remote repository. Default: all revisions.'),
    dict(name='--protocol', nargs='?', help='Transport protocol for the source control management. Supported: https, http, ssh, git. Default: inferred from URL.'),
    help='Add a library and its dependencies into the current %s or specified destination path.' % cwd_type)
def add(url, path=None, depth=None, protocol=None):
    repo = Repo.fromrepo()

    lib = Repo.fromurl(url, path)
    import_(lib.fullurl, lib.path, depth=depth, protocol=protocol, top=False)
    repo.scm.ignore(repo, relpath(repo.path, lib.path))
    lib.sync()

    lib.write()
    repo.scm.add(lib.lib)


@subcommand('remove', 
    dict(name='path', help="Local library name or path"),
    help='Remove specified library and its dependencies from the current %s.' % cwd_type)
def remove(path):
    repo = Repo.fromrepo()
    if not Repo.isrepo(path):
        error("Could not find library in path (%s)" % path, 1)

    lib = Repo.fromrepo(path)

    repo.scm.remove(lib.lib)
    rmtree_readonly(lib.path)
    repo.scm.unignore(repo, relpath(repo.path, lib.path))


# Publish command
@subcommand('publish',
    dict(name=['-A', '--all'], action="store_true", help="Publish all branches, including new. Default: push only the current branch."),
    help='Publish current %s and its dependencies to associated remote repository URLs.' % cwd_type)
def publish(all=None, top=True):
    if top:
        action("Checking for local modifications...")

    repo = Repo.fromrepo()
    if repo.is_local:
        error("%s \"%s\" in \"%s\" is a local repository.\nPlease associate it with a remote repository URL before attempting to publish.\nRead more about %s repositories here:\nhttp://developer.mbed.org/handbook/how-to-publish-with-%s/" % ("Program" if top else "Library", repo.name, repo.path, repo.scm.name, repo.scm.name), 1)

    for lib in repo.libs:
        if lib.check_repo():
            with cd(lib.path):
                progress()
                publish(False, all)

    sync(recursive=False)

    if repo.scm.dirty():
        action('Uncommitted changes in \"%s\" (%s)' % (repo.name, relpath(cwd_root, repo.path)))
        raw_input('Press enter to commit and push: ')
        repo.scm.commit()

    try:
        if repo.scm.outgoing():
            action("Pushing local repository \"%s\" to remote \"%s\"" % (repo.name, repo.url))
            repo.scm.push(repo, all)
    except ProcessException as e:
        if e[0] != 1:
            raise


# Update command
@subcommand('update',
    dict(name='rev', nargs='?', help="Revision hash, tag or branch"),
    dict(name=['-C', '--clean'], action="store_true", help="Perform a clean update and discard all local changes. WARNING: This action cannot be undone. Use with caution."),
    dict(name=['-F', '--force'], action="store_true", help="Enforce the original layout and will remove any local libraries and also libraries containing uncommitted or unpublished changes. WARNING: This action cannot be undone. Use with caution."),
    dict(name=['-I', '--ignore'], action="store_true", help="Ignore errors regarding unpiblished libraries, unpublished or uncommitted changes, and attempt to update from associated remote repository URLs."),
    dict(name='--depth', nargs='?', help='Number of revisions to fetch from the remote repository. Default: all revisions.'),
    dict(name='--protocol', nargs='?', help='Transport protocol for the source control management. Supported: https, http, ssh, git. Default: inferred from URL.'),
    help='Update current %s and its dependencies from associated remote repository URLs.' % cwd_type)
def update(rev=None, clean=False, force=False, ignore=False, top=True, depth=None, protocol=None):
    if top and clean:
        sync()
        
    repo = Repo.fromrepo()
    
    if top and not rev and repo.scm.isdetached():
        error("This %s is in detached HEAD state, and you won't be able to receive updates from the remote repository until you either checkout a branch or create a new one.\nYou can checkout a branch using \"%s checkout <branch_name>\" command before running \"mbed update\"." % (cwd_type, repo.scm.name),1)
    
    # Fetch from remote repo
    action("Updating %s \"%s\" to %s" % (cwd_type if top else cwd_dest, os.path.basename(repo.path) if top else relpath(cwd_root, repo.path), "rev #"+rev if rev else "latest revision in the current branch"))
    repo.scm.update(repo, rev, clean)
    repo.rm_untracked()

    # Compare library references (.lib) before and after update, and remove libraries that do not have references in the current revision
    for lib in repo.libs:
        if not os.path.isfile(lib.lib) and os.path.isdir(lib.path): # Library reference doesn't exist in the new revision. Will try to remove library to reproduce original structure
            gc = False
            with cd(lib.path):
                lib_repo = Repo.fromrepo(lib.path)
                gc, msg = lib_repo.can_update(clean, force)
            if gc:
                action("Removing library \"%s\" (obsolete)" % (relpath(cwd_root, lib.path)))
                rmtree_readonly(lib.path)
                repo.scm.unignore(repo, relpath(repo.path, lib.path))
            else:
                if ignore:
                    warning(msg)
                else:
                    error(msg, 1)

    # Reinitialize repo.libs() to reflect the library files after update
    repo.sync()
    
    # Recheck libraries as their URLs might have changed
    for lib in repo.libs:
        if os.path.isdir(lib.path) and Repo.isrepo(lib.path):
            lib_repo = Repo.fromrepo(lib.path)
            if lib.url != lib_repo.url: # Repository URL has changed
                gc = False
                with cd(lib.path):
                    gc, msg = lib_repo.can_update(clean, force)
                if gc:
                    action("Removing library \"%s\" (changed URL). Will add from new URL." % (relpath(cwd_root, lib.path)))
                    rmtree_readonly(lib.path)
                    repo.scm.unignore(repo, relpath(repo.path, lib.path))
                else:
                    if ignore:
                        warning(msg)
                    else:
                        error(msg, 1)

    # Import missing repos and update to hashes
    for lib in repo.libs:
        if not os.path.isdir(lib.path):
            import_(lib.fullurl, lib.path, depth=depth, protocol=protocol, top=False)
            repo.scm.ignore(repo, relpath(repo.path, lib.path))
        else:
            with cd(lib.path):
                update(lib.hash, clean, force, ignore, top=False)


# Synch command
@subcommand('sync',
    help='Synchronize dependency references (.lib files) in the current %s.' % cwd_type)
def sync(recursive=True, keep_refs=False, top=True):
    if top and recursive:
        action("Synchronizing dependency references...")
        
    repo = Repo.fromrepo()
    repo.scm.ignores(repo)

    for lib in repo.libs:
        if os.path.isdir(lib.path):
            lib.check_repo()
            lib.sync()
            lib.write()
            repo.scm.ignore(repo, relpath(repo.path, lib.path))
        else:
            if not keep_refs:
                action("Removing reference \"%s\" -> \"%s\"" % (lib.name, lib.fullurl))
                repo.scm.remove(lib.lib)
                repo.scm.unignore(repo, relpath(repo.path, lib.path))

    for root, dirs, files in os.walk(repo.path):
        dirs[:]  = [d for d in dirs  if not d.startswith('.')]
        files[:] = [f for f in files if not f.startswith('.')]

        for dir in list(dirs):
            if not Repo.isrepo(os.path.join(root, dir)):
                continue

            lib = Repo.fromrepo(os.path.join(root, dir))            
            if os.path.isfile(lib.lib):
                dirs.remove(dir)
                continue

            dirs.remove(dir)
            lib.write()
            repo.scm.ignore(repo, relpath(repo.path, lib.path))
            repo.scm.add(lib.lib)

    repo.sync()

    if recursive:
        for lib in repo.libs:
            if lib.check_repo():
                with cd(lib.path):
                    sync(keep_refs=keep_refs, top=False)

            
@subcommand('ls',
    dict(name=['-a', '--all'], action='store_true', help="List repository URL and hash pairs"),
    dict(name=['-I', '--ignore'], action="store_true", help="Ignore errors regarding missing libraries."),
    help='View the current %s dependency tree.' % cwd_type)
def list_(all=False, prefix='', p_path=None, ignore=False):
    repo = Repo.fromrepo()
    print prefix + (relpath(p_path, repo.path) if p_path else repo.name), '(%s)' % ((repo.fullurl if all else repo.hash) or 'no revision')

    for i, lib in enumerate(sorted(repo.libs, key=lambda l: l.path)):
        if prefix:
            nprefix = prefix[:-3] + ('|  ' if prefix[-3] == '|' else '   ')
        else:
            nprefix = ''
        nprefix += '|- ' if i < len(repo.libs)-1 else '`- '

        if lib.check_repo(ignore):
            with cd(lib.path):
                list_(all, nprefix, repo.path, ignore=ignore)


@subcommand('status',
    dict(name=['-I', '--ignore'], action="store_true", help="Ignore errors regarding missing libraries."),
    help='Show status of the current %s and its dependencies.' % cwd_type)
def status(ignore=False):
    repo = Repo.fromrepo()
    if repo.scm.dirty():
        action("Status for \"%s\":" % repo.name)
        print repo.scm.status()

    for lib in repo.libs:
        if lib.check_repo(ignore):
            with cd(lib.path):
                status(ignore)


@subcommand('compile',
    dict(name=['-t', '--toolchain'], help="Compile toolchain. Example: ARM, uARM, GCC_ARM, IAR"),
    dict(name=['-m', '--mcu'], help="Compile target. Example: K64F, NUCLEO_F401RE, NRF51822..."),
    dict(name='--tests', dest="compile_tests", action="store_true", help="Compile tests in TESTS directory."),
    help='Compile program using the native mbed OS build system.')
def compile(toolchain=None, mcu=None, compile_tests=False):
    root_path = Repo.findroot(os.getcwd())
    if not root_path:
        Repo.fromrepo()
    with cd(root_path):
        mbed_os_path = None
        if os.path.split(os.getcwd())[1] == 'mbed-os':
            mbed_os_path = "." 
        elif os.path.isdir('mbed-os'):
            mbed_os_path = "mbed-os" 
        if mbed_os_path is None:
            error('The mbed-os codebase and tools were not found in this program.', -1)

        args = remainder
        repo = Repo.fromrepo()
        file = os.path.join(repo.scm.store, 'mbed')

        target = mcu if mcu else get_cfg(file, 'TARGET')
        if target is None:
            error('Please specify compile target using the -m switch or set default target using command "target"', 1)
            
        tchain = toolchain if toolchain else get_cfg(file, 'TOOLCHAIN')
        if tchain is None:
            error('Please specify compile toolchain using the -t switch or set default toolchain using command "toolchain"', 1)

        macros = []
        if os.path.isfile('MACROS.txt'):
            with open('MACROS.txt') as f:
                macros = f.read().splitlines()

        env = os.environ.copy()
        env['PYTHONPATH'] = '.'

        # Only compile a program
        if mbed_os_path == 'mbed-os':
            popen(['python', os.path.join(mbed_os_path, 'tools', 'make.py')]
                + list(chain.from_iterable(izip(repeat('-D'), macros)))
                + ['-t', tchain, '-m', target, '--source=.', '--build=%s' % os.path.join('.build', target, tchain)]
                + args,
                env=env)
            # remove clean build flag onec exercised 
            if "-c" in args: args.remove('-c')
        else:
            action("Skipping module compilation as it is a library!")

        # Compile tests
        if compile_tests:
            tests_path = 'TESTS'
            if os.path.exists(tests_path):
                # Loop on test group directories
                for d in os.listdir(tests_path):
                    # dir name host_tests is reserved for host python scripts.
                    if d != "host_tests":
                        # Loop on test case directories
                        for td in os.listdir(os.path.join(tests_path, d)):
                            # compile each test
                            popen(['python', os.path.join(mbed_os_path, 'tools', 'make.py')]
                                + list(chain.from_iterable(izip(repeat('-D'), macros)))
                                + ['-t', tchain, '-m', target]
                                + ['--source=%s' % os.path.join(tests_path, d, td), '--source=.']
                                + ['--build=%s' % os.path.join('.build', target, tchain)]
                                + args,
                                env=env)
                            if "-c" in args: args.remove('-c')

# Test command
@subcommand('test',
    dict(name=['-l', '--list'], action="store_true", help="List all of the available tests"),
    help='Find and build tests in a project and its libraries.')
def test(list=False):
    # Find the root of the project
    root_path = Repo.findroot(os.getcwd())
    if not root_path:
        Repo.fromrepo()
    
    # Change directories to the project root to use mbed OS tools
    with cd(root_path):
        # If "mbed-os" folder doesn't exist, error
        if not os.path.isdir('mbed-os'):
            error('The mbed-os codebase and tools were not found in this program.', -1)
        
        # Gather remaining arguments and prepare environment variables
        args = remainder
        repo = Repo.fromrepo()
        env = os.environ.copy()
        env['PYTHONPATH'] = '.'
        
        if list:
            # List all available tests (by default in a human-readable format)
            try:
                popen(['python', 'mbed-os/tools/test.py', '-l'] + args,
                    env=env)
            except ProcessException as e:
                error('Failed to run test script')

# Export command
@subcommand('export',
    dict(name=['-i', '--ide'], help="IDE to create project files for. Example: UVISION,DS5,IAR", required=True),
    dict(name=['-m', '--mcu'], help="Export for target MCU. Example: K64F, NUCLEO_F401RE, NRF51822..."),
    help='Generate project files for desktop IDEs for the current program.')
def export(ide=None, mcu=None):
    root_path = Repo.findroot(os.getcwd())
    if not root_path:
        Repo.fromrepo()
    with cd(root_path):
        if not os.path.isdir('mbed-os'):
            error('The mbed-os codebase and tools were not found in this program.', -1)

        args = remainder
        repo = Repo.fromrepo()
        file = os.path.join(repo.scm.store, 'mbed')
        
        target = mcu if mcu else get_cfg(file, 'TARGET')
        if target is None:
            error('Please specify export target using the -m switch or set default target using command "target"', 1)

        macros = []
        if os.path.isfile('MACROS.txt'):
            with open('MACROS.txt') as f:
                macros = f.read().splitlines()

        env = os.environ.copy()
        env['PYTHONPATH'] = '.'
        popen(['python', 'mbed-os/tools/project.py']
            + list(chain.from_iterable(izip(repeat('-D'), macros)))
            + ['-i', ide, '-m', target, '--source=%s' % repo.path]
            + args,
            env=env)

        
# Build system and exporters
@subcommand('target',
    dict(name='name', nargs='?', help="Default target name. Example: K64F, NUCLEO_F401RE, NRF51822..."),
    help='Set default target for the current program.')
def target(name=None):
    root_path = Repo.findroot(os.getcwd())
    with cd(root_path):
        repo = Repo.fromrepo()
        file = os.path.join(repo.scm.store, 'mbed')
        if name is None:
            name = get_cfg(file, 'TARGET')
            action(('The default target for program "%s" is "%s"' % (repo.name, name)) if name else 'No default target is specified for program "%s"' % repo.name)
        else:        
            set_cfg(file, 'TARGET', name)
            action('"%s" now set as default target for program "%s"' % (name, repo.name))

@subcommand('toolchain',
    dict(name='name', nargs='?', help="Default toolchain name. Example: ARM, uARM, GCC_ARM, IAR"),
    help='Sets default toolchain for the current program.')
def toolchain(name=None):
    root_path = Repo.findroot(os.getcwd())
    with cd(root_path):
        repo = Repo.fromrepo()        
        file = os.path.join(repo.scm.store, 'mbed')
        if name is None:
            name = get_cfg(file, 'TOOLCHAIN')
            action(('The default toolchain for program "%s" is "%s"' % (repo.name, name)) if name else 'No default toolchain is specified for program "%s"' % repo.name)
        else:
            set_cfg(file, 'TOOLCHAIN', name)
            action('"%s" now set as default toolchain for program "%s"' % (name, repo.name))


# Parse/run command
if len(sys.argv) <= 1:
    parser.print_help()
    sys.exit(1)

args, remainder = parser.parse_known_args()

try:
    verbose = args.verbose
    log('Working path \"%s\" (%s)' % (os.getcwd(), cwd_type))
    status = args.command(args)
except ProcessException as e:
    error('Subrocess exit with error code %d' % e[0], e[0])
except OSError as e:
    if e[0] == 2:
        error('Could not detect one of the command-line tools.\nPlease verify that you have Git and Mercurial installed and accessible from your current path by executing commands "git" and "hg".\nHint: check the last executed command above.', e[0])
    else:
        error('OS Error: %s' % e[1], e[0])
except KeyboardInterrupt as e:
    error('User aborted!', 255)

sys.exit(status or 0)