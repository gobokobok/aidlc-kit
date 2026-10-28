## AIDLC Kit: working rules for the AI assistant

This repository uses AIDLC Kit to take features from discovery to an
engineering handoff. When the PM asks for an AIDLC step, by its command name
(such as /discover) or in their own words, follow these rules.

- Run the kit through its command-line tool: `aidlc <command> ...`. If `aidlc`
  is not found, try `.venv/bin/aidlc`. Never run `git` or `gh` yourself; the
  tool does that, including saving, sharing and review requests.
- If you cannot run terminal commands, give the PM the exact command to run
  and explain the result they paste back.
- Never edit `status`, `version`, `approvals`, `rejections`, `approved_tier` or
  `declared_tier` in files under `features/` by hand. The tool owns them.
- The PM never sees Git. Do not show command output verbatim unless they ask.
  Relay the tool's closing sentences in your own words, in one or two plain
  sentences: what happened and what comes next.
- You draft; people decide. Anything you write is a draft until approved.
  Show the PM the draft and ask before saving it if they gave you little to go on.
- Pass drafted text through standard input: `--body-file -` with a heredoc.
  Get the outline first with `aidlc template <type>` and keep its headings.
- If the tool exits with an error, explain the problem plainly and offer the fix.
- `aidlc --help` and `aidlc <command> --help` list every option.
