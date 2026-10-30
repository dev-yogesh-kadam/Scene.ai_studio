"""Public ids: what a link shows for a project, a module, an agent tab or a Claude session, in place of the database's
own numbers. A prefix says what the id is ("PRJ" a project, "MOD" a module, "AGT" an agent tab, "SES" a Claude
session), and random letters after it make it its own: PRJ7fK2mQ9xLt4wA."""

import secrets
import string

ALPHABET = string.ascii_letters + string.digits
SIZE = 13
PROJECT, MODULE, AGENT, SESSION = "PRJ", "MOD", "AGT", "SES"


def new(prefix):
    return prefix + "".join(secrets.choice(ALPHABET) for _ in range(SIZE))


def of_project(parent_id):
    """A new id for a project, or for a module when it is inside one."""
    return new(MODULE if parent_id else PROJECT)


def looks_like(ref, *prefixes):
    """Whether `ref` has the shape of an id (with one of `prefixes`, when they are given)."""
    ref = str(ref or "")
    return (len(ref) == 3 + SIZE and ref[3:].isalnum() and ref.isascii()
            and (ref[:3] in prefixes if prefixes else ref[:3] in (PROJECT, MODULE, AGENT, SESSION)))


def fill_projects(db):
    """Gives the projects and modules from before ids theirs."""
    for row in db.all("SELECT id, parent_id FROM projects WHERE ref = ''"):
        db.run("UPDATE projects SET ref = ? WHERE id = ?", (of_project(row["parent_id"]), row["id"]))
