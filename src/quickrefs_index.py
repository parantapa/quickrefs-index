"""Create index for Quick references.

A quick reference folder contains RST files with some extra annotations.
"""

from __future__ import annotations

import os
import re
import sys
import json
from itertools import pairwise
from typing import Optional

import click
from attrs import define
from cattrs import unstructure, structure
from dateutil.parser import parse

HEADING_CHARS = set("= - ` ' . ~ * + ^".split())


@define
class Heading:
    file: str
    line: int
    heading: str
    level: str


@define
class Reference:
    file: str
    line: int
    reference: str
    section: Optional[Heading]


@define
class Deadline:
    file: str
    line: int
    what: str
    when: str
    section: Optional[Heading]


@define
class Todo:
    file: str
    line: int
    what: str
    section: Optional[Heading]


@define
class Index:
    headings: list[Heading] = []
    references: list[Reference] = []
    deadlines: list[Deadline] = []
    todos: list[Todo] = []

    def save(self, fname: str):
        with open(fname, "wt") as fobj:
            d = unstructure(self)
            json.dump(d, fobj)

    @classmethod
    def load(cls, fname: str) -> Index:
        try:
            with open(fname, "rt") as fobj:
                index = json.load(fobj)
        except OSError as e:
            print(f"Error opening {fname}: {e}", file=sys.stderr)
            return cls()
        index = structure(index, cls)
        return index


def is_heading(curl: str, nextl: str) -> bool:
    curl = curl.rstrip()
    nextl = nextl.rstrip()

    if len(curl) < 3:
        return False

    if len(curl) != len(nextl):
        return False

    char0 = nextl[0]
    if char0 not in HEADING_CHARS:
        return False

    if nextl == char0 * len(nextl):
        return True

    return False


def parse_file(file: str, index: Index) -> None:
    """Parse a given file."""
    ref_pattern = re.compile(r"`(.*?)`_")
    dl_pattern = re.compile(r":deadline:`(.*?)`")
    todo_pattern = re.compile(r":todo:`(.*?)`")

    with open(file, "rt") as fobj:
        cur_heading = None
        for i, (curl, nextl) in enumerate(pairwise(fobj), 1):
            if is_heading(curl, nextl):
                cur_heading = Heading(
                    file=file, line=i, heading=curl.strip(), level=nextl[0]
                )
                index.headings.append(cur_heading)
                continue

            for ref in ref_pattern.findall(curl):
                ref = Reference(
                    file=file, line=i, reference=ref.strip(), section=cur_heading
                )
                index.references.append(ref)

            for dl in dl_pattern.findall(curl):
                when, what = dl.split(":", maxsplit=1)
                when, what = when.strip(), what.strip()
                dl = Deadline(
                    file=file, line=i, when=when, what=what, section=cur_heading
                )
                index.deadlines.append(dl)

            for todo in todo_pattern.findall(curl):
                todo = Todo(file=file, line=i, what=todo.strip(), section=cur_heading)
                index.todos.append(todo)


def get_files_to_parse(workdir: Optional[str]) -> list[str]:
    """Get the files to parse."""
    ofnames: list[str] = []

    if workdir is not None:
        os.chdir(workdir)

    for root, _, fnames in os.walk("."):
        for fname in fnames:
            if fname.endswith(".rst"):
                ofnames.append(os.path.join(root, fname))

    ofnames = sorted(set(ofnames))
    return ofnames


opt_workdir = click.option(
    "-C",
    "--chdir",
    "workdir",
    default=None,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="If provided switch to this directory first.",
)

opt_ofname = click.option(
    "-o",
    "--output",
    "ofname",
    default="index.json",
    show_default=True,
    help="Index file.",
)

opt_ifname = click.option(
    "-h",
    "--index-file",
    "ifname",
    default="index.json",
    show_default=True,
    help="Index file.",
)

opt_color = click.option(
    "-c",
    "--color",
    is_flag=True,
    show_default=True,
    help="Force color output",
)


@click.group()
def quickrefs_index():
    """Quick reference index."""


@quickrefs_index.command()
@opt_workdir
@opt_ofname
def build(workdir, ofname):
    """Build the index."""
    fnames = get_files_to_parse(workdir)
    index = Index()
    for fname in fnames:
        parse_file(fname, index)

    index.save(ofname)


@quickrefs_index.command()
@opt_ifname
@opt_color
def heading_jumplist(ifname, color):
    """Print the heading jumplist."""
    index = Index.load(ifname)

    if not color:
        color = None

    for h in index.headings:
        line = click.style(h.line, fg="green")
        fname = click.style(h.file, fg="yellow")
        if h.level in ("=", "-"):
            click.echo(f"{h.heading}\t{fname}\t{line}", color=color)


@quickrefs_index.command()
@opt_ifname
def print_all_headings(ifname):
    """Print all headings."""
    index = Index.load(ifname)

    for h in index.headings:
        if h.level in ("=", "-"):
            click.echo(h.heading)


@quickrefs_index.command()
@opt_ifname
@click.argument("heading")
def jump_to_heading(ifname, heading):
    """Print the jumplist for given heading."""
    index = Index.load(ifname)

    for h in index.headings:
        if heading == h.heading:
            click.echo(f"{h.file}\t{h.line}")


@quickrefs_index.command()
@opt_ifname
@opt_color
def deadline_jumplist(ifname, color):
    """Print the deadline jumplist"""
    index = Index.load(ifname)

    if not color:
        color = None

    for d in sorted(index.deadlines, key=lambda h: parse(h.when)):
        line = click.style(d.line, fg="green")
        fname = click.style(d.file, fg="yellow")
        if d.section is None:
            label = f"{d.when}: {d.what}"
        else:
            heading = click.style(d.section.heading, fg="cyan")
            label = f"{heading}: {d.when}: {d.what}"

        click.echo(f"{label}\t{fname}\t{line}", color=color)


@quickrefs_index.command()
@opt_ifname
@opt_color
def todo_jumplist(ifname, color):
    """Print the todo jumplist."""
    index = Index.load(ifname)

    if not color:
        color = None

    for t in index.todos:
        line = click.style(t.line, fg="green")
        fname = click.style(t.file, fg="yellow")
        if t.section is None:
            label = f"{t.what}"
        else:
            heading = click.style(t.section.heading, fg="cyan")
            label = f"{heading}: {t.what}"

        click.echo(f"{label}\t{fname}\t{line}", color=color)
