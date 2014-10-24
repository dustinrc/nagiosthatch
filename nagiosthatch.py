#!/usr/bin/env python


"""
    nagiosthatch
    ~~~~~~~~~~~~

    An attempt to view Nagios object relations and inheritance.
"""


from __future__ import print_function

from collections import defaultdict
from functools import partial
from os import walk
import os.path as op
from pprint import pprint
import re
import string
import sys

def print_stderr(obj):
    print("ERROR: {0}".format(obj), file=sys.stderr)

try:
    import argparse
except ImportError as e:
    print_stderr(e)
    print_stderr("Please install the argparse module from PyPI.")
    sys.exit(1)


def merge_paths(path, new_pardir='.', merge='.'):
    stripped_path = op.relpath(path, start=merge)
    return op.join(new_pardir, stripped_path)

def parse_to_graph(cfg_files, key='use', directives=['\S*'], strict_key=False):
    graphdd = defaultdict(list)

    directive_pat_tmpl = r'^\s*(?P<directive>{0})\s*(?P<value>[^;]+)\s*'
    directive_pats = map(directive_pat_tmpl.format, directives)
    directive_res = map(re.compile, directive_pats)
    comment_only_pat = r'^\s*[#;].*$'
    comment_only_re = re.compile(comment_only_pat)
    start_curly_pat = r'^\s*define\s*(?P<obj_type>\S*)\s*{.*$'
    start_curly_re = re.compile(start_curly_pat)
    end_curly_pat = r'}'
    end_curly_re = re.compile(end_curly_pat)
    lists_pat = r'_host_name_aliases|contact_groups|hostgroup_name|hostgroups|members|parents|use'
    lists_re = re.compile(lists_pat)

    for f in cfg_files:
        directives = {}
        with open(f, 'r') as cfg_file:
            for line in map(string.strip, cfg_file.readlines()):
                if re.search(comment_only_re, line):
                    continue

                match_obj_type = start_curly_re.match(line)
                if match_obj_type:
                    motgd = match_obj_type.groupdict()
                    directives['__obj_type'] = motgd['obj_type']
                    continue

                if re.search(end_curly_re, line):

                    directives['__filename'] = f
                    collection_key = directives.get(key, f)
                    if strict_key and collection_key is f:
                        continue

                    if type(collection_key) is list and all(map(lambda x: isinstance(x, str), collection_key)):
                        for kc in collection_key:
                            graphdd[kc].append(directives)
                    elif isinstance(collection_key, str):
                        graphdd[collection_key].append(directives)
                    else:
                        print_stderr('cannot use collection_key: {0}'.format(collection_key))

                    directives = {}
                    continue

                for directive_re in directive_res:
                    match = directive_re.match(line)
                    if match:
                        mgd = match.groupdict()
                        drctv = mgd['directive'].strip()
                        vl = mgd['value'].strip()
                        if re.search(lists_re, drctv):
                            directives[drctv] = re.split(r'(\+)|\s*,\s*|\s*', vl)
                            directives[drctv] = filter(lambda x: bool(x), directives[drctv])
                        else:
                            directives[drctv] = vl
                        continue

    return dict(graphdd)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('nagios_cfg_file', metavar='CFG',
                        help='Nagios configuration file')
    parser.add_argument('-dh', '--detail-host', metavar='HOST',
                        help='provide inheritance detail for a specific host')
    parser.add_argument('-k', '--key',
                        help='the key (directive) for association')
    parser.add_argument('-sk', '--strict-key', action='store_true',
                        help='the key (directive) must be in the object')
    parser.add_argument('-m', '--merge', metavar='PATH',
                        help='merge absolute path of cfg_dirs into parent' + \
                        'directory of the Nagios configuration file\'s path')

    args = parser.parse_args()
    cfg_dirs = []
    cfg_files = []

    with open(args.nagios_cfg_file, 'r') as cfg_file:
        for line in map(string.strip, cfg_file.readlines()):
            if line.startswith('cfg_dir'):
                cfg_dirs.append(line.split('=')[1].strip())
            if line.startswith('cfg_file'):
                cfg_files.append(line.split('=')[1].strip())

    if args.merge:
        nagios_cfg_pardir = op.dirname(args.nagios_cfg_file)
        merge_in = partial(merge_paths, new_pardir=nagios_cfg_pardir,
                                 merge=args.merge)
        cfg_dirs = map(merge_in, cfg_dirs)
        cfg_files = map(merge_in, cfg_files)

    for cfg_dir in cfg_dirs:
        for root, dirs, files in walk(cfg_dir):
            for filepath in map(lambda x: op.join(root, x), files):
                if filepath.endswith('.cfg'):
                    cfg_files.append(filepath)
                else:
                    print_stderr('skipping {0}'.format(filepath))
        cfg_files.sort()

    if args.key:
        graph = parse_to_graph(cfg_files, key=args.key,
                               strict_key=args.strict_key)
        print('\n*** organized by key ***')
        pprint(graph)

    if args.detail_host:
        host_graph = parse_to_graph(cfg_files, key='host_name')
        name_graph = parse_to_graph(cfg_files, key='name')
        obj = host_graph.get(args.detail_host, None)

        def drill_down(obj, name_graph):
            inheritance_order = []
            if obj is not None:
                obj = obj[0]
                inheritance_order.append(obj.get('name', ''))
                for parent in obj.get('use', []):
                    i_o = drill_down(name_graph.get(parent, None), name_graph)
                    inheritance_order.extend(i_o)
            return inheritance_order

        inheritance_order = drill_down(obj, name_graph)
        for parent in inheritance_order:
            if parent is '' or parent is '+':
                continue
            parent_obj = name_graph.get(parent, [{}])
            parent_obj[0].update(obj[0])
            obj = parent_obj
        print('\n*** host inheritance detail for {0} ***'.format(args.detail_host))
        pprint(obj)


if __name__ == '__main__':
    main()
