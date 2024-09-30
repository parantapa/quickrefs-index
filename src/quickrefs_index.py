"""Create index for Quick references.

A quick reference folder contains RST files with some extra annotations.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from datetime import datetime
from itertools import pairwise

import click
from pydantic import BaseModel, Field
from dateutil.parser import parse

HEADING_CHARS = set("= - ` ' . ~ * + ^".split())


class Heading(BaseModel):
    file: str
    line: int
    heading: str
    level: str


class Reference(BaseModel):
    file: str
    line: int
    reference: str
    section: Heading | None


class Deadline(BaseModel):
    file: str
    line: int
    what: str
    when: str
    section: Heading | None


class Todo(BaseModel):
    file: str
    line: int
    what: str
    section: Heading | None


class Index(BaseModel):
    headings: list[Heading] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    deadlines: list[Deadline] = Field(default_factory=list)
    todos: list[Todo] = Field(default_factory=list)

    def save(self, fname: Path):
        fname.write_text(self.model_dump_json())

    @classmethod
    def load(cls, fname: Path) -> Index:
        try:
            return cls.model_validate_json(fname.read_text())
        except OSError as e:
            print(f"Error opening {fname}: {e}", file=sys.stderr)
            return cls()


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


def parse_file(file: Path, index: Index) -> None:
    """Parse a given file."""
    ref_pattern = re.compile(r"`(.*?)`_")
    dl_pattern = re.compile(r":deadline:`(.*?)`")
    todo_pattern = re.compile(r":todo:`(.*?)`")

    with open(file, "rt") as fobj:
        cur_heading = None
        for i, (curl, nextl) in enumerate(pairwise(fobj), 1):
            if is_heading(curl, nextl):
                cur_heading = Heading(
                    file=str(file), line=i, heading=curl.strip(), level=nextl[0]
                )
                index.headings.append(cur_heading)
                continue

            for ref in ref_pattern.findall(curl):
                ref = Reference(
                    file=str(file), line=i, reference=ref.strip(), section=cur_heading
                )
                index.references.append(ref)

            for dl in dl_pattern.findall(curl):
                when, what = dl.split(":", maxsplit=1)
                when, what = when.strip(), what.strip()
                dl = Deadline(
                    file=str(file), line=i, when=when, what=what, section=cur_heading
                )
                index.deadlines.append(dl)

            for todo in todo_pattern.findall(curl):
                todo = Todo(
                    file=str(file), line=i, what=todo.strip(), section=cur_heading
                )
                index.todos.append(todo)


def get_files_to_parse(workdir: Path | None) -> list[Path]:
    """Get the files to parse."""
    ofnames: list[Path] = []

    if workdir is None:
        workdir = Path.cwd()

    dirpath: Path
    filenames: list[str]
    for dirpath, _, filenames in workdir.walk():
        for fname in filenames:
            if fname.endswith(".rst"):
                ofnames.append(dirpath / fname)

    ofnames = sorted(set(ofnames))
    return ofnames


opt_workdir = click.option(
    "-C",
    "--chdir",
    "workdir",
    default=None,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="If provided switch to this directory first.",
)

opt_ofname = click.option(
    "-o",
    "--output",
    "ofname",
    default="index.json",
    type=click.Path(exists=False, file_okay=True, dir_okay=False, path_type=Path),
    show_default=True,
    help="Index file.",
)

opt_ifname = click.option(
    "-h",
    "--index-file",
    "ifname",
    default="index.json",
    type=click.Path(exists=False, file_okay=True, dir_okay=False, path_type=Path),
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
        days = (parse(d.when) - datetime.today()).days
        if d.section is None:
            label = f"{d.when} ({days}d): {d.what}"
        else:
            heading = click.style(d.section.heading, fg="cyan")
            label = f"{heading}: {d.when} ({days}d): {d.what}"

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
