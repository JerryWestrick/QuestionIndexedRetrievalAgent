# KePrompt — the harness QIRA runs under

QIRA is consumed via [keprompt](https://github.com/JerryWestrick/keprompt), an LLM harness CLI. Not a full keprompt reference — only the parts QIRA exercises, plus the gotchas that have already bitten us. For creating new external functions, see `~/keprompt/ks/creating-keprompt-functions.context.md` (per memory `reference_keprompt_functions.md`).

## What keprompt is, in one line

A terminal-native LLM runner that reads `.prompt` files, dispatches tool calls to external-function executables, records every conversation (messages, tool calls, costs) to SQLite, and exposes the whole trace via `keprompt chat show`.

## Install + initialize a project

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install keprompt
keprompt init
```

`pip install keprompt` installs the CLI. `keprompt init` scaffolds the **current working directory** as a keprompt project. CWD = project root; there is no separate "keprompt project" concept beyond "the dir you ran `keprompt init` in". Per memory `feedback_keprompt_usage.md`: always run keprompt from the project dir.

### What `init` produces

```
.
└── prompts
    ├── chats.db                                    # SQLite — all chat history, costs, messages
    ├── hello.prompt                                # sample starter prompt
    └── functions
        ├── functions.json                          # function registry
        ├── keprompt_builtins.py                    # keprompt's built-in functions
        ├── keprompt_builtins.py                    # another built-in
        ├── render_url_to_markdown.py               # sample external function
        └── model_prices_and_context_window.json    # LiteLLM model DB, ~2600 models
```

- `init` **requires internet** on first run — downloads the LiteLLM model price DB.
- `prompts/functions/` is the auto-discovery directory for external functions. Dropping `qira` (from a corpus zip) into this directory is enough for keprompt to find it on the next run.
- `chats.db` is the authoritative record of every conversation. Never modified by `qira`; all writes come from keprompt itself.

## `.prompt` file format — the keywords QIRA uses

`.prompt` files are line-oriented. Each line starts with a dot-keyword and the rest of the line is the argument. Keywords QIRA actually uses:

| Keyword | Purpose | Example |
|---|---|---|
| `.prompt` | Prompt header — name, version, model/params as JSON-ish fragment | `.prompt "name":"qira-test", "version":"1.0", "params":{"model":"openai/gpt-4o-mini"}` |
| `.functions` | Declare which external functions are in scope; supports wildcards | `.functions qira.*` |
| `.system` | System message | `.system You are a helpful assistant.` |
| `.include` | Include another file's contents (full path from project root) | `.include prompts/functions/qira.prompt` |
| `.user` | User message | `.user How do I pretty-print JSON?` |
| `.exec` | Execute the prompt against the LLM | `.exec` |
| `.exit` | End of prompt. Auto-appended by keprompt if omitted. | `.exit` |

A minimal QIRA test prompt that works end-to-end:

```
.prompt "name":"qira-test", "version":"1.0", "params":{"model":"openai/gpt-4o-mini"}
.functions qira.*
.system You are a helpful assistant. When a user question could be answered from an available corpus, use qira_search and qira_read to ground your answer and cite the section IDs.
.include prompts/functions/qira.prompt
.user Using the provided documentation; Lookup how do I pretty-print JSON in Python?
.exec
```

The canonical working example is `QUICKSTART.md` step 6c.

## Ordering rules that bit us

These caused a full debug loop in session 2026-04-11. Do not forget them.

1. **`.functions` must come before `.system` / `.user`.** Function declarations are part of model setup and are locked before any messages are emitted. Declaring them after `.system` silently fails to register.
2. **Use `.functions qira.*` (wildcard), not `.functions qira`.** Bare `qira` looks for a single function literally named `qira` and finds none. The wildcard expands to the actual function names the executable declares via `--list-functions` (e.g. `qira_search`, `qira_read`). Confirm in `vm_state.allowed_functions` in a `chat show` trace.
3. **`.include` paths are project-root-relative.** `.include prompts/functions/qira.prompt` works. `.include functions/qira.prompt` does **not** — keprompt does not implicitly resolve against `prompts/`.

## Variable substitution

Variables are passed via `--set key value` on the CLI and referenced as `<<key>>` in the prompt body. Delimiters are configurable via the `Prefix` / `Postfix` variables (see `vm_state.variables` in a trace), but the defaults are `<<` and `>>`.

Real-world example — the eu-ai-act builder's call in `examples/eu-ai-act/build_corpus.py:869`:

```python
argv = [
    "keprompt", "chat", "new",
    "--prompt", "generate_questions",
    "--set", "breadcrumb", section.breadcrumb,
    "--set", "title", section.title,
    "--set", "content", content,
]
```

And the prompt body in `examples/eu-ai-act/generate_questions.prompt` contains `<<breadcrumb>>`, `<<title>>`, `<<content>>` tokens at the `.user` line. KePrompt substitutes before execution.

(The `<<var>>` syntax is observed from the builder, not read from canonical keprompt docs. If it changes, update this file.)

## External function protocol

KePrompt discovers external functions by scanning `prompts/functions/` at startup. Any executable found there that implements the protocol below is registered.

**Discovery:** keprompt invokes the executable with `--list-functions` and parses stdout as a JSON array of OpenAI function-calling schema objects. Example from `runtime/qira`:

```bash
./prompts/functions/qira --list-functions
# → [{"name":"qira_search","description":"...","parameters":{...}}, {"name":"qira_read",...}]
```

**Invocation:** When the LLM emits a tool call, keprompt spawns the executable with the function name as the first argument, pipes the call's JSON arguments on stdin, and reads stdout as the tool result (text or markdown).

```bash
echo '{"corpus":"python-stdlib","question":"..."}' | ./prompts/functions/qira qira_search
```

**Error protocol:** non-zero exit + stderr text. KePrompt catches it and delivers the stderr content to the LLM as a `tool_result`, so error messages should read well to an LLM (e.g. `Error: unknown corpus 'foo'. Available: python-stdlib, eu-ai-act`). Reference implementation: `runtime/qira:386`.

**Venv sensitivity:** external functions with a generic `#!/usr/bin/env python3` shebang inherit whatever `python3` is on `PATH` when keprompt spawns them. If keprompt is run from a non-activated venv shell, the external function's Python imports will fail. Always run keprompt from an activated venv. This is how `runtime/qira` is wired.

## Running a prompt + inspecting the result

**Run:**

```bash
keprompt chat new --prompt <name>
```

`<name>` is the filename under `prompts/` **without** the `.prompt` extension and **without** the `prompts/` prefix. Per memory `feedback_keprompt_usage.md`: prompt names, not paths.

**Summary line on completion** (format observed in real runs):

```
Chat 24820074:1 with openai:openai/gpt-4o-mini Total Cost: $0.000739 (In: $0.000538, Out: $0.000200) Wall: 15.06s API: 11.84s
Context: Input 3,588/128,000 (2.8%) Output 334/16,384 (2.0%)
```

The first number (`24820074`) is the chat ID. Note it.

**Inspect the full trace:**

```bash
keprompt chat show <chat_id>
```

Dumps the entire conversation record as JSON, pretty-printed. This is the authoritative debug tool for plumbing failures. Anatomy of the output:

| Path | Contents |
|---|---|
| `costs[]` | One entry per `.exec` round: tokens in/out, cost, elapsed, model, provider, success flag |
| `messages[]` | Every message in order: `system`, `user`, `assistant` (text or tool calls), `tool` (results). Tool calls carry `id`, `name`, `arguments`; tool results carry `tool_use_id` and `content`. |
| `vm_state.allowed_functions` | The resolved function list. If `.functions qira.*` is in the prompt, this is the authoritative "what the wildcard expanded to". |
| `vm_state.status` | `ok` on success, something else on failure |
| `vm_state.variables.model_info` | Full model metadata — `function_calling`, `parallel_function_calling`, `max_input_tokens`, etc. Use this to check whether the model actually supports the tool-calling features your prompt relies on. |
| `statements[]` | The parsed prompt script — confirms how keprompt interpreted each line |

When a plumbing test fails, always run `chat show {id}` before theorizing. The `messages` array tells you exactly which tool call was made with which arguments and what came back.

Parallel tool calls are supported — a single `assistant` message may contain multiple tool-call entries in its `content` array. Real observed example: `gpt-4o-mini` issued `qira_read` on `python-stdlib:1.1.2` and `python-stdlib:1` in parallel after a single `qira_search`.

## LLM credentials

KePrompt speaks to providers via LiteLLM. Env var conventions are LiteLLM's — typically `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `CEREBRAS_API_KEY`, etc. For the authoritative list and any keprompt-specific overrides, check `keprompt --help` or the keprompt repo docs. Don't fabricate env var names — ask the user or read the config.

## Known gotchas

1. **Venv activation.** If the external function fails with `ModuleNotFoundError`, the venv is not active when keprompt was invoked. See "Venv sensitivity" above.
2. **`.functions` wildcard.** `.functions qira` ≠ `.functions qira.*`. The former is a literal name, the latter is a prefix match.
3. **`.functions` ordering.** Must precede `.system` / `.user`.
4. **`.include` paths.** Project-root-relative, not `prompts/`-relative.
5. **Model tool-call support.** Some models silently ignore tool definitions. Verify `vm_state.variables.model_info.supports.function_calling == true` before debugging "LLM never calls any qira function".
6. **`keprompt init` needs internet.** First run downloads the LiteLLM model DB. Fails silently-ish on an air-gapped box.
7. **`chats.db` is the truth.** Terminal output is a rendering. When the terminal summary and `chat show` disagree, trust `chat show`.
