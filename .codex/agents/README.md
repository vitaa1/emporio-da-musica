# Development reviewers

These project-scoped Codex agents assist development; the store application still
uses the planned single-agent architecture. They inherit the parent model and
reasoning settings. No provider, credentials, application dependencies, or global
agent settings are added.

| Agent | When to request it |
| --- | --- |
| `code_reviewer` | Before a PR: correctness, regressions, acceptance criteria, and meaningful tests. |
| `security_reviewer` | Changes to customer data, authorization, LLM/tool inputs, secrets, dependencies, or CI permissions. |

Start a new Codex session in this repository if an existing session does not expose
the new agents. Request a specific agent and an explicit scope, for example:

```text
Use code_reviewer to review the committed diff main...HEAD. Do not edit files.
Use security_reviewer to review the pending changes in src/controller.py and its tests. Do not edit files.
```

For uncommitted work, provide the file list and explicitly include relevant untracked
files. A branch-only diff cannot cover them. Reviewers report file/line evidence,
impact, and suggested corrections in Portuguese. The primary developer verifies
findings and applies fixes; reviewers do not approve or merge PRs.

Both roles prohibit edits and external mutations by instruction. Custom agents
inherit the parent's sandbox, approval policy, and tool permissions; these files
are not a separate enforcement boundary. For filesystem-enforced read-only review,
start a separate session with:

```sh
codex --sandbox read-only --ask-for-approval never
```

The filesystem sandbox does not by itself prevent remote mutations through connected
services. Keep the review scoped and avoid granting unnecessary integrations.

Existing `tdd` and `diagnosing-bugs` skills remain implementation/diagnosis workflows;
reviewers need not invoke them or run their mutation steps. Agent reviews supplement
CI and human judgment and do not guarantee correctness or security.

Configuration follows the [official custom-agent schema](https://learn.chatgpt.com/docs/agent-configuration/subagents).
The files were checked with Python's TOML parser against the documented required
fields. Both reviewer instruction sets were executed through delegated agents for issue #3
and reported no confirmed findings in its documentation scope. This exercised their
instructions; automatic discovery of these TOML files in a fresh Codex session has
not yet been verified.
