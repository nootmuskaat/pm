-- Basic schema for our project management database
PRAGMA foreign_keys = ON; -- SQLite3 doesn't enforce foreign keys by default

CREATE TABLE issues (
    issue_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    created_time INT NOT NULL, -- Unix time
    created_by TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    assigned_to TEXT,
    status TEXT NOT NULL, -- 'open', 'in progress', 'pending', 'closed'
    closed INTEGER,
    closed_time INTEGER
);


CREATE TABLE comments (
    comment_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER NOT NULL,
    created_time INTEGER NOT NULL, -- Unix time
    created_by TEXT NOT NULL,
    comment_text TEXT NOT NULL,
    FOREIGN KEY(issue_id) REFERENCES issues(issue_id)
);
CREATE INDEX comments_idx ON comments(issue_id);

CREATE TABLE tags (
    issue_id INTEGER NOT NULL,
    tag TEXT,
    FOREIGN KEY(issue_id) REFERENCES issues(issue_id)
);
CREATE INDEX tags_idx ON tags(issue_id);

CREATE TABLE checked_out (
    username TEXT NOT NULL,
    issue_id INTEGER NOT NULL,
    FOREIGN KEY(issue_id) REFERENCES issues(issue_id)
);
CREATE INDEX checked_out_idx ON checked_out(username);

CREATE TABLE issue_history ( -- this table is for all history other than creation
    username TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    issue_id INTEGER NOT NULL,
    FOREIGN KEY(issue_id) REFERENCES issues(issue_id)
);
CREATE INDEX history_issue_idx ON issue_history(issue_id);
CREATE INDEX history_user_idx ON issue_history(username);
