#!/usr/bin/env python
"""
Very basic ticket management tool
Written by nootmuskaat
"""

import argparse
import logging
import sqlite3
import subprocess

from datetime import datetime
from getpass import getuser
from pprint import pformat
from random import randint
from re import findall
from os import remove as rm

ACTIONS = {
    "assign": "Assign the issue (defaults to self)",
    "checkout": "Checkout an issue (make it your default)",
    "close": "Close an issue",
    "comment": "Add a comment to an issue",
    "current": "Show currently checked-out issue",
    "help": "Show available actions (this)",
    "list": "List issues (only open by default)",
    "modify": "Modify title, description, or tags of an issue",
    "new": "Create a new issue",
    "reopen": "Re-open a closed issue",
    "status": "Change the issue status (open, in progress, or pending)"
    }
DB = "test.db"
try:
    CONN = sqlite3.connect(DB)
except sqlite3.OperationalError:
    CONN = None
TIMESTAMP = datetime.now().strftime("%s")
USERNAME = getuser()

class PMError(Exception):
    """Exception caught/raised by this module"""
    pass

def _cliargs():
    """Return CLI argument namespace"""
    parser = argparse.ArgumentParser(prog="pm", add_help=False)
    # actions and their descriptions
    parser.add_argument("action", type=str)
    # parameters to be passed to actions
    params = parser.add_argument_group("parameters")
    params.add_argument("--all", action="store_true")
    params.add_argument("-a", "--assign", type=str, nargs="?",
                        const=USERNAME, dest="assigned_to")
    params.add_argument("-d", "--description", type=str)
    params.add_argument("-f", "--format", type=str)
    params.add_argument("-h", "--help", action="store_true")
    params.add_argument("-i", "--issue", type=int, dest="issue_id")
    params.add_argument("-m", "--message", type=str, dest="comment_text")
    params.add_argument("--since", type=str)
    params.add_argument("-s", "--status", type=str,
                        choices=["open", "pending", "in progress"])
    params.add_argument("-t", "--title", type=str)
    params.add_argument("--tag", type=str, action="append")
    # return a dictionary of only those arguments that have been passed
    args = parser.parse_args()
    if args.action not in ACTIONS:
        logging.error("invalid action %s", args.action)
        args.action = "help" # redirect to help
    if args.issue_id and not verify_issue(args.issue_id):
        raise PMError("Please provide a valid issue id")
    return {k: v for k, v in args.__dict__.items() if v}

def left_align(text):
    """Returns a multiline string left-aligned"""
    lines = text.split("\n")
    return "\n".join([line.lstrip() for line in lines])

def run_help(_):
    """Return program help string"""
    text = """Please select from the following options:
    (call with -h to get action specific help)

    ACTIONS\n"""
    for act_, help_ in ACTIONS.items():
        line = "{} : {}\n".format(act_.ljust(8), help_)
        text += line
    return left_align(text)

def run_status(args):
    """Change the status of an issue
    Options:
    -i : the issue_id to reopen (default: checked out)
    -m : optional comment
    -s : status"""
    # Establish issue_id to close
    issue_id = args.get("issue_id") or fetch_checkedout()
    if not issue_id:
        raise PMError("Please provide an issue_id")
    if not args.get("status"):
        raise PMError("Please provide a status")
    # Optional comment
    if "comment_text" in args:
        _ = db_insert(table="comments", db_dict={
            "comment_text": args["comment_text"],
            "created_time": TIMESTAMP,
            "created_by": USERNAME,
            "issue_id": issue_id
            })
    # Update issue history
    _ = db_insert(table="issue_history", db_dict={
        "issue_id": issue_id,
        "username": USERNAME,
        "timestamp": TIMESTAMP,
        "field": "status",
        "old_value": issue_field(issue_id, "status"),
        "new_value": args["status"]
        })
    # Update issue
    db_update(table="issues", issue_id=issue_id, db_dict={
        "status": args["status"]})
    CONN.commit()
    return {"issue_id": issue_id, "status": issue_field(issue_id, "status")}

def run_modify(args):
    """Modify the description, status, title or tags of an issue in vim
    Options:
    -i : issue id (defaults to checked-out)"""
    issue_id = args.get("issue_id") or fetch_checkedout()
    if not issue_id:
        raise PMError("Please provide an issue_id")
    # Note the old data
    old = {}
    old["title"] = issue_field(issue_id, "title")
    old["description"] = issue_field(issue_id, "description")
    old["tags"] = issue_tags(issue_id) or set()
    # Allow manipulation of the current information within vi
    tmpfile = "/tmp/pm_edit_{}_{}_{}_{}".format(
        issue_id, USERNAME, TIMESTAMP, randint(1, 1000000))
    template = "[title]\n{}\n[description]\n{}\n[tags]\n{}\n"
    with open(tmpfile, "w") as tmp:
        tmp.write(template.format(
            old["title"], old["description"], ",".join(old["tags"])))
    with open(tmpfile, "r+") as tmp:
        subprocess.call(["/usr/bin/vim", tmp.name])
    with open(tmpfile, "r") as tmp:
        new_text = tmp.read()
    rm(tmpfile)
    new = {}
    template = r"\[title\]\n(.*?)\n\[description\]\n(.*?)\n\[tags\]\n(.*?)"
    try:
        new["title"], new["description"], tags = findall(template, new_text)[0]
        new["tags"] = set([tag.strip() for tag in tags.split(",")])
    except IndexError:
        raise PMError("Unable to read changes")
    # update issue histories
    updates = {}
    for field in ["title", "description"]:
        if old[field] != new[field]:
            updates[field] = new[field]
            _ = db_insert(table="issue_history", db_dict={
                "username": USERNAME,
                "timestamp": TIMESTAMP,
                "field": field,
                "old_value": old[field],
                "new_value": new[field],
                "issue_id": issue_id
                })
    # update the issue
    if not updates:
        return updates
    db_update(table="issues", issue_id=issue_id, db_dict=updates)
    # update tags
    for tag in new["tags"].difference(old["tags"]):
        _ = db_insert(table="tags", db_dict={
            "issue_id": issue_id, "tag": tag})
    for tag in old["tags"].difference(new["tags"]):
        drop_tag(issue_id, tag)
    CONN.commit()
    return pformat(updates)


def run_list(args):
    """TODO"""
    pass

def run_current(args):
    """TODO"""
    pass

def run_reopen(args):
    """Reopen a closed issue
    Options:
    -i : the issue_id to reopen (default: checked out)
    -m : optional comment"""
    # Establish issue_id to close
    issue_id = args.get("issue_id") or fetch_checkedout()
    if not issue_id:
        raise PMError("Please provide an issue_id")
    # Optional comment
    if "comment_text" in args:
        _ = db_insert(table="comments", db_dict={
            "comment_text": args["comment_text"],
            "created_time": TIMESTAMP,
            "created_by": USERNAME,
            "issue_id": issue_id
            })
    # Update issue history
    _ = db_insert(table="issue_history", db_dict={
        "issue_id": issue_id,
        "username": USERNAME,
        "timestamp": TIMESTAMP,
        "field": "status",
        "old_value": "closed",
        "new_value": "open"
        })
    # Update issue
    db_update(table="issues", issue_id=issue_id, db_dict={
        "status": "open", "closed": 0, "closed_time": None})
    CONN.commit()
    return {"issue_id": issue_id, "closed": False}



def run_checkout(args):
    """Checkout an issue, making it the default for most actions.
    Options:
    -i : issue_id"""
    try:
        issue_id = args["issue_id"]
    except KeyError:
        raise PMError("Please provide an issue id")
    if fetch_checkedout():
        db_update(table="checked_out", username=USERNAME, db_dict={
            "issue_id": issue_id})
    else:
        _ = db_insert(table="checked_out", db_dict={
            "issue_id": issue_id, "username": USERNAME})
    CONN.commit()
    return {"issue_id": issue_id, "username": USERNAME}


def run_comment(args):
    """Add a comment to an issue.
    Options:
    -i : issue id (default: checked-out)
    -m : comment message"""
    # Establish issue_id for comment
    if "comment_text" not in args:
        raise PMError("Please provide a comment with -m")
    issue_id = args.get("issue_id") or fetch_checkedout()
    if not issue_id:
        raise PMError("Please provide a issue_id")
    # Insert in comments
    comment_id = db_insert(table="comments", db_dict={
        "issue_id": issue_id,
        "created_time": TIMESTAMP,
        "created_by": USERNAME,
        "comment_text": args["comment_text"]
        })
    CONN.commit()
    return {"comment_id": comment_id, "issue_id": issue_id,
            "comment": args["comment_text"]}


def run_assign(args):
    """Assign an issue to a user. Note: assigning to "-" will unassign the
    issue. Also, this will not prevent you from "reassigning" the issue to
    the same user as is currently assigned.
    Options:
    -i : id of issue to assign
    -a : username"""
    # Establish issue_id to assign
    if "issue_id" not in args:
        raise PMError("Please provide an issue_id")
    if "assigned_to" not in args:
        raise PMError("Please provide an assignee")
    issue_id = args["issue_id"]
    if args["assigned_to"] == "-":
        args["assigned_to"] = None
    # Update issue history
    _ = db_insert(table="issue_history", db_dict={
        "issue_id": issue_id,
        "username": USERNAME,
        "timestamp": TIMESTAMP,
        "field": "status",
        "old_value": issue_field(issue_id, "assigned_to"),
        "new_value": args["assigned_to"]
        })
    # Update issue
    db_update(table="issues", issue_id=issue_id, db_dict={
        "assigned_to": args["assigned_to"]
        })
    CONN.commit()
    return {"issue_id": issue_id, "assigned_to": args["assigned_to"]}

def run_new(args):
    """Create a new issue
    Options:
    -a : username of assignee (default: self)
    -d : new issue description
    -s : set issue status (default: 'open')
         values: ['open', 'in progress', 'pending']
    -t : title of new issue
    --tag : attach the tag to the issue"""
    # Create a complete dict
    issue = {
        "closed": 0,
        "created_by": USERNAME,
        "created_time": TIMESTAMP,
        "status": "open",
        "tag": [],
        "title": "untitled issue"
        }
    fields = ["assigned_to", "description", "status", "title", "tag"]
    received = {k: v for k, v in args.items() if k in fields}
    logging.debug("Received parameters: %s", received)
    issue.update(received)
    logging.debug("Creation parameters: %s", issue)
    # Prepare for INSERT into database
    tags = issue.pop("tag")
    issue_id = db_insert("issues", issue)
    issue["issue_id"] = issue_id
    for tag in tags:
        _ = db_insert(table="tags",
                      db_dict={"issue_id": issue_id, "tag": tag})
    CONN.commit()
    return pformat(issue)

def run_close(args):
    """Close an issue
    Options:
    -i : the issue_id to close (default: checked out)
    -m : closing comment"""
    # Establish issue_id to close
    issue_id = args.get("issue_id") or fetch_checkedout()
    if not issue_id:
        raise PMError("Please provide a issue_id")
    # Optional comment
    if "comment_text" in args:
        _ = db_insert(table="comments", db_dict={
            "comment_text": args["comment_text"],
            "created_time": TIMESTAMP,
            "created_by": USERNAME,
            "issue_id": issue_id
            })
    # Update issue history
    _ = db_insert(table="issue_history", db_dict={
        "issue_id": issue_id,
        "username": USERNAME,
        "timestamp": TIMESTAMP,
        "field": "status",
        "old_value": issue_field(issue_id, "status"),
        "new_value": "closed"
        })
    # Update issue
    db_update(table="issues", issue_id=issue_id, db_dict={
        "status": "closed", "closed": 1, "closed_time": TIMESTAMP})
    CONN.commit()
    return {"issue_id": issue_id, "closed": True}


def db_update(table, db_dict, issue_id=None, username=None):
    """Update rows matching issue_id/username on table according to db_dict"""
    statement = "UPDATE {} SET {} WHERE "
    if issue_id:
        statement += "issue_id=?;"
    elif username:
        statement += "username=?;"
    # column1=?,column2=?,...
    column_text = ",".join(
        ["=".join([c, "?"]) for c in db_dict.keys()]
        )
    values = list(db_dict.values()) + [issue_id]
    # Update issue
    cur = CONN.cursor()
    try:
        cur.execute(statement.format(table, column_text), tuple(values))
    except sqlite3.OperationalError as exc:
        raise PMError(exc)
    finally:
        cur.close()

def db_insert(table, db_dict):
    """Inserts the information contained in db_dict into table.
    Returns the row id of the inserted column."""
    # format the SQL statement
    columns, values = [], []
    for col, val in db_dict.items():
        columns.append(col)
        values.append(val)
    column_text = ", ".join(columns)
    # (?, ?, ...) for safe-handling
    value_text = ", ".join(["?"]*len(columns))
    base = "INSERT INTO {} ({}) VALUES ({});"
    statement = base.format(table, column_text, value_text)
    # Execute and commit statement
    cur = CONN.cursor()
    try:
        cur.execute(statement, tuple(values))
    except sqlite3.OperationalError as exc:
        raise PMError(exc)
    else:
        id_ = cur.lastrowid
    finally:
        cur.close()
    return id_

def fetch_checkedout(username=None):
    """Return the checked-out issue_id of the current user"""
    if not username:
        username = USERNAME
    statement = "SELECT issue_id FROM checked_out where username = ?;"
    cur = CONN.cursor()
    cur.execute(statement, (username,))
    try:
        issue_id = cur.fetchone()[0]
    except TypeError:
        return None
    else:
        return issue_id
    finally:
        cur.close()

def issue_tags(issue_id):
    """Return list of tags associated with an issue id"""
    cur = CONN.cursor()
    statement = "SELECT tag FROM tags WHERE issue_id=? ORDER BY tag;"
    cur.execute(statement, (issue_id,))
    tags = set([row[0] for row in cur.fetchall()])
    cur.close()
    return tags

def issue_field(issue_id, field):
    """Returns the value of field for issue_id's entry in issues table"""
    cur = CONN.cursor()
    statement = "SELECT {} FROM issues WHERE issue_id=?;".format(field)
    cur.execute(statement, (issue_id,))
    try:
        status = cur.fetchone()[0]
    except TypeError:
        status = None
    cur.close()
    return status

def verify_issue(issue_id):
    """Return bool of whether issue_id is valid"""
    cur = CONN.cursor()
    cur.execute("SELECT issue_id from issues where issue_id=?;", (issue_id,))
    valid = bool(cur.fetchone())
    cur.close()
    return valid

def drop_tag(issue_id, tag):
    """Remove a tag from an issue"""
    cur = CONN.cursor()
    cur.execute("DELETE FROM tags WHERE issue_id=? AND tag=?;",
                (issue_id, tag,))
    cur.close()
    return


def verify_connection(conn):
    """Verify that the connection is to a database with an issues table
    Returns: bool"""
    if not conn:
        return False
    cur = conn.cursor()
    try:
        cur.execute("select issue_id from issues;")
    except sqlite3.OperationalError:
        logging.fatal("Unable to connect to database %s", DB)
        return False
    else:
        return True
    finally:
        cur.close()

def _main():
    """MAIN"""
    try:
        args = _cliargs()
        logging.debug("CLI call: %s", args)
        help_needed = args["action"] == "help" or "help" in args
        good_connection = verify_connection(CONN)
        if not help_needed and not good_connection:
            raise PMError("Invalid database")
        run = eval("run_{}".format(args["action"]))
        if "help" in args:
            print(left_align(run.__doc__))
        print(run(args))
    except PMError as exc:
        print(exc)
    finally:
        if CONN:
            CONN.close()

if __name__ == "__main__":
    _main()
