#!/usr/bin/env python

import os
import sys
from argparse import ArgumentParser
from glob import glob
from os.path import join
from pathlib import Path

import gv
import yaml

__version__ = "0.1.0"
__author__ = "Sebastien Nicouleaud"


def parse_args(args):
    """Parse the command-line arguments and return a config object.

        >>> config = parse_args(['-o', 'schema.jpg',
        ...                      '-f', 'jpg',
        ...                      'roles/',
        ...                      '../other/roles'])
        >>> config.output
        'schema.jpg'
        >>> config.format
        'jpg'
        >>> config.roles_dirs
        ['roles/', '../other/roles']

    Provides sane defaults:

        >>> config = parse_args([])
        >>> config.output
        'ansible-roles.png'
        >>> config.format
        'png'
        >>> config.roles_dirs
        ['roles']
    """
    p = ArgumentParser(description="Generate a picture of ansible roles graph.")

    p.add_argument(
        "roles_dirs",
        metavar="ROLES_DIR|PLAYBOOK",
        type=str,
        nargs="*",
        default=["roles"],
        help="a directory containing ansible roles or a playbook",
    )

    p.add_argument(
        "-o", "--output", type=str, default="ansible-roles.png", help="the output file"
    )

    p.add_argument("-f", "--format", type=str, default=None, help="file format")

    p.add_argument(
        "-x",
        "--exclude",
        type=str,
        default="",
        help="Colon separated list of roles that should not be displayed",
    )

    # If no format was specified use the file extension
    parsed = p.parse_args(args)
    if parsed.format is None:
        parsed.format = Path(parsed.output).suffix[1:]
    return parsed


def extract_str(obj, name):
    if isinstance(obj, str):
        return obj
    else:
        return obj[name]


class GraphBuilder:
    def __init__(self, filter=lambda: []):
        self.graph = gv.digraph("roles")
        self._role_nodes = {}
        self._links = {}
        self._filter = filter

    def __create_node__(self, label):
        if label not in self._role_nodes:
            self._role_nodes[label] = gv.node(self.graph, label)
        return self._role_nodes[label]

    def add_role(self, role):
        if role not in self._filter:
            self.__create_node__(role)

    def add_playbook(self, role):
        if role not in self._filter:
            node = self.__create_node__(role)
            gv.setv(node, "shape", "parallelogram")

    def link_roles(self, dependent_role, depended_role):
        if depended_role in self._filter or depended_role in self._filter:
            return
        if (dependent_role, depended_role) not in self._links:
            gv.edge(self._role_nodes[dependent_role], self._role_nodes[depended_role])
            self._links[(dependent_role, depended_role)] = True


def parse_files_or_dirs(targets, builder=GraphBuilder()):
    for path in targets:
        path = Path(path)
        if os.path.isdir(path):
            parse_role_dir(path, builder)
        elif os.path.isfile(path):
            parse_playbook(path, builder)
        else:
            raise ValueError("Can't read file", path)
    return builder.graph


def parse_role_dir(roles_dir, builder):
    for path in glob(join(roles_dir, "*")):
        parse_role(path, builder)


def parse_playbook(path, builder):
    playbook_name = path.name
    playbook_dir = path.parent
    builder.add_playbook(playbook_name)
    with open(path, "r") as f:
        playbook_data = yaml.safe_load(f.read()) or {}

    # Search for included playbooks and used roles
    roles = set()
    for group in playbook_data:
        for role in group.get("roles", []):
            roles.add(extract_str(role, "role"))
        included_play = group.get("import_playbook")
        if included_play:
            incl_play_path = playbook_dir / included_play
            parse_playbook(incl_play_path, builder)
            builder.link_roles(playbook_name, included_play)
    for role in roles:
        parse_role(playbook_dir / "roles" / role, builder)
        builder.link_roles(playbook_name, role)


def parse_role(role_path, builder=GraphBuilder()):
    path_meta = role_path / "meta" / "main.yml"
    role_name = role_path.name

    builder.add_role(role_name)

    # Find dependencies
    if os.path.exists(path_meta):
        with open(path_meta, "r") as f:
            data = yaml.safe_load(f.read()) or {}
            for dependency in data.get("dependencies", []):
                depended_role = extract_str(dependency, "role")
                builder.add_role(depended_role)
                builder.link_roles(role_name, depended_role)

    # Find included roles
    path_tasks = role_path / "tasks" / "main.yml"
    if os.path.exists(path_tasks):
        with open(path_tasks, "r") as f:
            data = yaml.safe_load(f.read()) or []
            for e in data:
                incl_role = e.get("include_role")
                if incl_role:
                    included_role = incl_role["name"]

                    builder.add_role(included_role)
                    builder.link_roles(role_name, included_role)


def render_graph(graph, config):
    gv.layout(graph, "dot")
    gv.render(graph, config.format, config.output)


def main():
    config = parse_args(sys.argv[1:])
    builder = GraphBuilder(config.exclude.split(","))
    graph = parse_files_or_dirs(config.roles_dirs, builder)
    render_graph(graph, config)


if __name__ == "__main__":
    main()
