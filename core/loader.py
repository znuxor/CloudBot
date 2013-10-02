import collections
import glob
import os
import re
import traceback

from core import main


if 'mtimes' not in globals():
    mtimes = {}

if 'lastfiles' not in globals():
    lastfiles = set()


def make_signature(f):
    return f.func_code.co_filename, f.func_name, f.func_code.co_firstlineno


def format_plug(plug, kind='', lpad=0):
    out = ' ' * lpad + '{}:{}:{}'.format(*make_signature(plug[0]))
    if kind == 'command':
        out += ' ' * (50 - len(out)) + plug[1]['name']

    if kind == 'event':
        out += ' ' * (50 - len(out)) + ', '.join(plug[1]['events'])

    if kind == 'regex':
        out += ' ' * (50 - len(out)) + plug[1]['regex']

    return out


def reload(bot, init=False):
    changed = False

    if init:
        bot.plugins = collections.defaultdict(list)
        bot.threads = {}

    fileset = set(glob.glob(os.path.join('plugins', '*.py')))

    # remove deleted/moved plugins
    for name, data in bot.plugins.iteritems():
        bot.plugins[name] = [x for x in data if x[0]._filename in fileset]

    for filename in list(mtimes):
        if filename not in fileset and filename not in core_fileset:
            mtimes.pop(filename)

    for func, handler in list(bot.threads.iteritems()):
        if func._filename not in fileset:
            main.handler.stop()
            del bot.threads[func]

    # compile new plugins
    for filename in fileset:
        mtime = os.stat(filename).st_mtime
        if mtime != mtimes.get(filename):
            mtimes[filename] = mtime

            changed = True

            try:
                code = compile(open(filename, 'U').read(), filename, 'exec')
                namespace = {}
                eval(code, namespace)
            except Exception:
                traceback.print_exc()
                continue

            # remove plugins already loaded from this filename
            for name, data in bot.plugins.iteritems():
                bot.plugins[name] = [x for x in data
                                   if x[0]._filename != filename]

            for func, handler in list(bot.threads.iteritems()):
                if func._filename == filename:
                    handler.stop()
                    del bot.threads[func]

            for obj in namespace.itervalues():
                if hasattr(obj, '_hook'):  # check for magic
                    if obj._thread:
                        bot.threads[obj] = main.Handler(bot, obj)

                    for type, data in obj._hook:
                        bot.plugins[type] += [data]

                        if not init:
                            print '### new plugin (type: %s) loaded:' % \
                                  type, format_plug(data)

    if changed:
        bot.commands = {}
        for plug in bot.plugins['command']:
            name = plug[1]['name'].lower()
            if not re.match(r'^\w+$', name):
                print '### ERROR: invalid command name "{}" ({})'.format(name, format_plug(plug))
                continue
            if name in bot.commands:
                print "### ERROR: command '{}' already registered ({}, {})".format(name,
                                                                                   format_plug(bot.commands[name]),
                                                                                   format_plug(plug))
                continue
            bot.commands[name] = plug

        bot.events = collections.defaultdict(list)
        for func, args in bot.plugins['event']:
            for event in args['events']:
                bot.events[event].append((func, args))

    if init:
        print '  plugin listing:'

        if bot.commands:
            # hack to make commands with multiple aliases
            # print nicely

            print '    command:'
            commands = collections.defaultdict(list)

            for name, (func, args) in bot.commands.iteritems():
                commands[make_signature(func)].append(name)

            for sig, names in sorted(commands.iteritems()):
                names.sort(key=lambda x: (-len(x), x))  # long names first
                out = ' ' * 6 + '%s:%s:%s' % sig
                out += ' ' * (50 - len(out)) + ', '.join(names)
                print out

        for kind, plugs in sorted(bot.plugins.iteritems()):
            if kind == 'command':
                continue
            print '    {}:'.format(kind)
            for plug in plugs:
                print format_plug(plug, kind=kind, lpad=6)
        print
