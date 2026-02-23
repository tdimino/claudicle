---
name: switch-soul
description: "Switch between soul profiles. Lists available profiles if no name given, or switches to the named profile."
disable-model-invocation: true
---

# Switch Soul Profile

Switch between named soul profiles in the Claudicle multi-soul system.

## Available Profiles

!`python3 "${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/soul-profiles.py" list 2>/dev/null || echo "No profiles directory. Run: python3 scripts/soul-profiles.py create <name>"`

## Current Profile

!`python3 "${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/soul-profiles.py" current 2>/dev/null || echo "default (soul/soul.md)"`

## Instructions

### If the user provided a profile name:

1. Switch the profile:
```bash
python3 "${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/soul-profiles.py" switch "<PROFILE_NAME>"
```

2. Reload the soul identity in the running session:
```bash
cd "${CLAUDICLE_HOME:-$HOME/.claudicle}/daemon" && python3 -c "
from engine import context
import config
context.invalidate_soul_cache()
context.reload_soul_path()
config.set_active_soul('<PROFILE_NAME>')
print(f'Soul switched to: {config.SOUL_NAME}')
print(f'Soul path: {context._SOUL_MD_PATH}')
"
```

3. Read the new soul personality file and adopt this identity for the remainder of the session.

4. Print:
```
Soul switched to <PROFILE_NAME>. Identity reloaded.
```

### If no profile name was given:

Show the available profiles list above and ask which profile to switch to.

### Creating a new profile:

```bash
python3 "${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/soul-profiles.py" create "<NAME>" [--from /path/to/template.md]
```

## Soul Journal

View the soul's evolution history:
```bash
python3 "${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/soul-profiles.py" journal
```
