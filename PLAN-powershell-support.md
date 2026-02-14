# Plan: Add PowerShell Support to shtab

## Background

shtab generates **static** shell tab-completion scripts from `argparse.ArgumentParser`
objects. It currently supports bash, zsh, and tcsh. PowerShell support has been listed
as a desired contribution in both README.rst and docs/index.md.

PowerShell uses `Register-ArgumentCompleter -Native` to register completion for
non-PowerShell (native) commands. The registered script block receives the partial
input and returns `[CompletionResult]` objects. Because shtab generates static
scripts (no runtime Python execution on every TAB press), all completion logic
must be embedded in the generated PowerShell script itself.

---

## Architecture Overview

Follow the exact pattern established by bash/zsh/tcsh:

```
argparse.ArgumentParser
  → get_powershell_commands(parser, root_prefix)   # extract structure
  → complete_powershell(parser, ...)                # @mark_completer("powershell")
  → Template.safe_substitute(...)                   # emit .ps1 script
  → str (PowerShell completion script)
```

The generated script uses `Register-ArgumentCompleter -Native -CommandName <prog>`.

---

## Step-by-step Changes

### Step 1: Register PowerShell in CHOICE_FUNCTIONS

**File:** `shtab/__init__.py` (line 40-42)

Add `"powershell"` key to each entry in `CHOICE_FUNCTIONS`:

```python
CHOICE_FUNCTIONS: Dict[str, Dict[str, str]] = {
    "file": {
        "bash": "_shtab_compgen_files",
        "zsh": "_files",
        "tcsh": "f",
        "powershell": "_shtab_powershell_compgen_files",   # NEW
    },
    "directory": {
        "bash": "_shtab_compgen_dirs",
        "zsh": "_files -/",
        "tcsh": "d",
        "powershell": "_shtab_powershell_compgen_dirs",    # NEW
    },
}
```

These names reference helper functions that will be defined inside the generated
PowerShell script template (Step 4).

---

### Step 2: Add `get_powershell_commands()` data-extraction function

**File:** `shtab/__init__.py` (insert before `complete_powershell`)

This function recursively walks the parser tree — identical in purpose to
`get_bash_commands()` — but produces data structures suited for PowerShell
template substitution.

**Returns** (per-prefix dictionaries keyed by prefix string):

| Key | Type | Description |
|-----|------|-------------|
| `subparsers` | `dict[str, list[str]]` | Maps prefix → list of subcommand names |
| `option_strings` | `dict[str, list[str]]` | Maps prefix → list of option strings |
| `compgens` | `dict[str, str]` | Maps `{prefix}_pos_{i}` or `{prefix}_{opt}` → completer function name |
| `choices` | `dict[str, list[str]]` | Maps `{prefix}_pos_{i}` or `{prefix}_{opt}` → list of valid choices |
| `nargs` | `dict[str, str]` | Maps `{prefix}_{action}` → nargs value |

The recursive traversal logic mirrors `get_bash_commands()` lines 166-291:

```python
def get_powershell_commands(root_parser, root_prefix, choice_functions=None):
    choice_type2fn = {k: v["powershell"] for k, v in CHOICE_FUNCTIONS.items()}
    if choice_functions:
        choice_type2fn.update(choice_functions)

    def recurse(parser, prefix):
        # Walk positionals: discover subparsers, choices, compgens
        # Walk optionals: collect option strings, choices, compgens
        # Return aggregated results
        ...  # STUB — follow get_bash_commands() structure exactly

    return recurse(root_parser, root_prefix)
```

**Implementation guidance:** The function can actually reuse `get_bash_commands()`
output format directly (list of formatted assignment strings) since the template
will embed them as PowerShell hashtable entries. **Alternatively**, for a cleaner
approach, produce Python dicts/lists that the template function serializes into
PowerShell syntax. The latter is recommended for maintainability.

---

### Step 3: Add `complete_powershell()` completer function

**File:** `shtab/__init__.py` (insert after `complete_tcsh`, before `complete()`)

```python
@mark_completer("powershell")
def complete_powershell(parser, root_prefix=None, preamble="", choice_functions=None):
    """
    Returns PowerShell syntax autocompletion script.

    See `complete` for arguments.
    """
    root_prefix = wordify(f"_shtab_{root_prefix or parser.prog}")
    # ... extract data, build template variables, return Template(...).safe_substitute(...)
```

This decorator call automatically:
- Appends `"powershell"` to `SUPPORTED_SHELLS`
- Registers the function in `_SUPPORTED_COMPLETERS["powershell"]`

---

### Step 4: Design the PowerShell completion script template

This is the core of the implementation. The generated `.ps1` script must:

1. Define hashtables for subparsers, options, choices, compgens, and nargs
2. Define helper functions for file/directory completion
3. Register a `ScriptBlock` via `Register-ArgumentCompleter -Native`
4. Inside the script block: parse the current command line, track parser state,
   and return `[CompletionResult]` objects

#### Template skeleton (PowerShell):

```powershell
# AUTOMATICALLY GENERATED by `shtab`

${preamble}

# --- Completion data (hashtables) ---
$${root_prefix}_subparsers = ${subparsers_hashtable}
$${root_prefix}_option_strings = ${option_strings_hashtable}
$${root_prefix}_compgens = ${compgens_hashtable}
$${root_prefix}_choices = ${choices_hashtable}
$${root_prefix}_nargs = ${nargs_hashtable}

# --- Helper functions ---
function _shtab_powershell_compgen_files {
    param($WordToComplete)
    Get-ChildItem -Path "$WordToComplete*" -File -ErrorAction SilentlyContinue |
        ForEach-Object { $_.Name }
    Get-ChildItem -Path "$WordToComplete*" -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { $_.Name }
}

function _shtab_powershell_compgen_dirs {
    param($WordToComplete)
    Get-ChildItem -Path "$WordToComplete*" -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { $_.Name }
}

# --- Main completer ---
Register-ArgumentCompleter -Native -CommandName ${prog} -ScriptBlock {
    param($wordToComplete, $commandAst, $cursorPosition)

    # Tokenize the command line
    $tokens = $commandAst.CommandElements | ForEach-Object { $_.ToString() }
    $tokens = $tokens[1..($tokens.Count - 1)]  # skip program name

    # State tracking
    $prefix = '${root_prefix}'
    $completedPositionals = 0
    $currentActionNargs = 1
    $currentActionArgsConsumed = 0
    $posOnly = $false

    $subparsers = $${root_prefix}_subparsers
    $optionStrings = $${root_prefix}_option_strings
    $compgens = $${root_prefix}_compgens
    $choices = $${root_prefix}_choices
    $nargs = $${root_prefix}_nargs

    # Walk tokens (excluding the word being completed)
    $completingIndex = $tokens.Count  # last token is the one being completed
    if ($wordToComplete -eq '') { $completingIndex = $tokens.Count }
    # ... STUB: port the bash state machine (lines 405-436 of current bash template)
    # Key logic:
    #   - If token matches a subparser name: update $prefix, reset state
    #   - If token matches an option string: set current action to that option
    #   - Track nargs to know when current action is "full"
    #   - Handle "--" for positional-only mode

    # Generate completions
    $completions = @()

    if (-not $posOnly -and $wordToComplete.StartsWith('-')) {
        # Complete option strings
        $currentOptions = $optionStrings[$prefix]
        $completions = $currentOptions | Where-Object { $_ -like "$wordToComplete*" }
    } else {
        # Complete positional args: subparsers, choices, or compgen functions
        $currentSubparsers = $subparsers[$prefix]
        if ($currentSubparsers) {
            $completions += $currentSubparsers | Where-Object { $_ -like "$wordToComplete*" }
        }

        $choiceKey = "${prefix}_pos_${completedPositionals}"
        $currentChoices = $choices[$choiceKey]
        if ($currentChoices) {
            $completions += $currentChoices | Where-Object { $_ -like "$wordToComplete*" }
        }

        $compgenKey = "${prefix}_pos_${completedPositionals}"  # or option key
        $compgenFunc = $compgens[$compgenKey]
        if ($compgenFunc) {
            $completions += & $compgenFunc $wordToComplete
        }
    }

    # Emit CompletionResult objects
    $completions | ForEach-Object {
        [System.Management.Automation.CompletionResult]::new(
            $_,                # completionText
            $_,                # listItemText
            'ParameterValue',  # resultType
            $_                 # toolTip
        )
    }
}
```

#### Key design decisions:

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Data format | PowerShell hashtables (`@{}`) | Natural key-value lookup; mirrors bash's associative arrays |
| Completion API | `Register-ArgumentCompleter -Native` | Standard PowerShell API for non-cmdlet commands |
| Return type | `CompletionResult` objects | Enables tooltips, proper display in Ctrl+Space menu |
| File completion | Custom functions (not cmdlets) | Allows user override via preamble; matches bash pattern |
| PowerShell version | 5.1+ (Desktop & Core) | `Register-ArgumentCompleter` available since PS 5.0 |
| Variable scoping | Script-scoped (`$script:`) or unique prefix | Avoid collisions in user's session |

#### Python-side serialization helpers needed:

```python
def _powershell_hashtable(d):
    """Serialize a dict[str, list[str]] to PowerShell @{} syntax."""
    # @{ 'key1' = @('val1', 'val2'); 'key2' = @('val3') }
    ...

def _powershell_flat_hashtable(d):
    """Serialize a dict[str, str] to PowerShell @{} syntax."""
    # @{ 'key1' = 'val1'; 'key2' = 'val2' }
    ...
```

---

### Step 5: Update examples with PowerShell preamble entries

**Files:**
- `examples/customcomplete.py` — add `"powershell"` key to `TXT_FILE` and `PREAMBLE`
- `examples/pathcomplete.py` — no changes needed (uses `shtab.FILE`/`shtab.DIRECTORY`)

```python
# In customcomplete.py
TXT_FILE = {
    "bash": "_shtab_greeter_compgen_TXTFiles",
    "zsh": "_files -g '(*.txt|*.TXT)'",
    "tcsh": "f:*.txt",
    "powershell": "_shtab_greeter_compgen_TXTFiles",  # NEW
}
PREAMBLE = {
    "bash": "...",
    "zsh": "",
    "tcsh": "",
    "powershell": """                                   # NEW
function _shtab_greeter_compgen_TXTFiles {
    param($WordToComplete)
    Get-ChildItem -Path "$WordToComplete*" -Include '*.txt','*.TXT' -File -ErrorAction SilentlyContinue |
        ForEach-Object { $_.Name }
    Get-ChildItem -Path "$WordToComplete*" -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { $_.Name }
}
""",
}
```

---

### Step 6: Add tests

**File:** `tests/test_shtab.py`

PowerShell is automatically included in all `@fix_shell`-parametrized tests
once `"powershell"` is added to `SUPPORTED_SHELLS` (via `@mark_completer`).

Tests that currently do shell-specific assertions use `if shell == "bash":` guards.
Add corresponding `elif shell == "powershell":` blocks where appropriate.

#### 6a. Smoke tests (all `@fix_shell` tests pass without error)

These already work by virtue of parametrization — they just call `shtab.complete(parser, shell=shell)` and verify no exceptions. This covers:
- `test_main`
- `test_complete`
- `test_positional_choices`
- `test_custom_complete`
- `test_subparser_custom_complete`
- `test_subparser_aliases`
- `test_subparser_colons`
- `test_subparser_slashes`
- `test_add_argument_to_optional`
- `test_add_argument_to_positional`
- `test_get_completer`
- etc.

#### 6b. Output validation tests

Add assertions for PowerShell-specific output markers:

```python
# In test_main_self_completion — add expected output:
expected = {
    "bash": "complete -o filenames -F _shtab_shtab shtab",
    "zsh": "_shtab_shtab_commands()",
    "tcsh": "complete shtab",
    "powershell": "Register-ArgumentCompleter -Native -CommandName shtab",  # NEW
}

# In test_prog_scripts — add expected output:
elif shell == "powershell":
    assert script_py == [
        "Register-ArgumentCompleter -Native -CommandName script.py -ScriptBlock {"
    ]  # or similar identifying line
```

#### 6c. (Optional / future) Integration tests with `pwsh`

If `pwsh` (PowerShell Core) is available in CI, add a `PowerShell` test helper
class similar to the existing `Bash` class:

```python
class PowerShell:
    def __init__(self, init_script=""):
        self.init = init_script

    def test(self, cmd, failure_message=""):
        init = self.init + "\n" if self.init else ""
        proc = subprocess.Popen(
            ["pwsh", "-NoProfile", "-Command", f"{init}{cmd}"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate()
        assert proc.wait() == 0, f"{failure_message}\n{cmd}\n{stdout}\n{stderr}"
```

This is **optional** for the initial implementation and can be deferred.

---

### Step 7: Update documentation

**Files to update:**

| File | Change |
|------|--------|
| `README.rst` | Add PowerShell to supported shells list; remove from Contributions wishlist |
| `docs/index.md` | Same as README |
| `docs/use.md` | Add PowerShell tab (=== "powershell") with installation instructions |
| `shtab/main.py` | No code change needed — `SUPPORTED_SHELLS` is used dynamically |
| `pyproject.toml` | No change needed — shell list is dynamic |

#### PowerShell installation instructions (for `docs/use.md`):

```powershell
# Generate and save to profile
shtab --shell=powershell my_app.main.get_main_parser | Out-File -FilePath $PROFILE -Append

# Or save to a file and dot-source it
shtab --shell=powershell my_app.main.get_main_parser | Out-File -FilePath ~\my_app_completion.ps1
. ~\my_app_completion.ps1
```

---

## File Change Summary

| File | Type of Change |
|------|---------------|
| `shtab/__init__.py` | Add `CHOICE_FUNCTIONS["powershell"]`, `get_powershell_commands()`, `complete_powershell()`, serialization helpers |
| `examples/customcomplete.py` | Add `"powershell"` entries to `TXT_FILE` and `PREAMBLE` |
| `tests/test_shtab.py` | Add PowerShell-specific assertions in `test_main_self_completion`, `test_prog_scripts`, `test_prog_override`; optionally add `PowerShell` helper class |
| `README.rst` | Update supported shells |
| `docs/index.md` | Update supported shells |
| `docs/use.md` | Add PowerShell installation tab |

---

## Implementation Order & Stubbing Strategy

The user asked to **prioritize stubbing** where implementation is uncertain.
Here is the recommended order, marking what can be fully implemented vs. stubbed:

| Order | Component | Status | Notes |
|-------|-----------|--------|-------|
| 1 | `CHOICE_FUNCTIONS` update | **Full impl** | Trivial dict addition |
| 2 | `@mark_completer("powershell")` registration | **Full impl** | One decorator |
| 3 | `get_powershell_commands()` | **Stub → Full** | Start as thin wrapper around `get_bash_commands()` reusing its output format, then refine |
| 4 | PowerShell serialization helpers | **Full impl** | `_powershell_hashtable()`, `_powershell_flat_hashtable()` |
| 5 | `complete_powershell()` template | **Stub** | Generate a syntactically valid script with `Register-ArgumentCompleter`. The state machine inside the ScriptBlock (token walking, nargs tracking) is the hardest part and should be stubbed with TODO markers |
| 6 | Tests (smoke) | **Full impl** | Parametrized tests auto-include powershell |
| 7 | Tests (output validation) | **Full impl** | Simple string matching |
| 8 | Tests (integration with `pwsh`) | **Stub** | Mark as `@pytest.mark.skipif(not shutil.which("pwsh"))` |
| 9 | Examples | **Full impl** | Dict entries |
| 10 | Docs | **Full impl** | Markdown additions |

### What to stub in the ScriptBlock template:

The generated PowerShell ScriptBlock has three layers of complexity:

1. **Easy (implement fully):** Option string completion (`-like "$wordToComplete*"`)
2. **Medium (implement):** Subcommand routing (walk tokens, match against subparser names)
3. **Hard (stub with TODO):** Full nargs tracking state machine; `--` positional-only mode; action-specific compgen dispatch

The stub should produce a **working script** that handles basic option and
subcommand completion, with TODO comments marking where nargs tracking and
advanced positional completion need to be finished.

---

## PowerShell Completion Behavior Reference

For implementors — how PowerShell native completion works:

```
Register-ArgumentCompleter -Native -CommandName <prog> -ScriptBlock {
    param($wordToComplete, $commandAst, $cursorPosition)

    # $wordToComplete  : the partial word being completed (string)
    # $commandAst      : AST of the entire command line
    # $cursorPosition  : integer cursor position

    # Return CompletionResult objects:
    [System.Management.Automation.CompletionResult]::new(
        $completionText,   # text inserted on Tab
        $listItemText,     # text shown in menu (Ctrl+Space)
        'ParameterValue',  # CompletionResultType enum
        $toolTip           # tooltip on hover
    )
}
```

Works in PowerShell 5.1+ (Windows) and PowerShell Core 7.x (cross-platform).
