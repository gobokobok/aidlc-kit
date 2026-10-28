# Shared rules for AIDLC slash commands

Every slash command in .claude/commands/ follows these rules. They are not a command.

- Run the kit through its CLI: `aidlc <command> ...`. If `aidlc` is not found,
  use `.venv/bin/aidlc`. Never run `git` or `gh` yourself; the CLI does that.
- The PM never sees Git. Do not show command output verbatim unless they ask.
  Relay the CLI's closing sentences in your own words, in one or two plain
  sentences: what happened and what comes next.
- You draft; people decide. Anything you write is a draft until approved.
  Show the PM the draft and ask before saving it if they gave you little to go on.
- Pass drafted text through standard input: `--body-file -` with a heredoc.
  Get the outline first with `aidlc template <type>` and keep its headings.
- If the CLI exits with an error, explain the problem plainly and offer the fix.
