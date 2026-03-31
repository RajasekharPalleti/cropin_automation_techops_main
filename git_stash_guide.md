# Git Stash Guide: How to Save & Retrieve Changes

This guide outlines how to safely store your current work in Git without committing it, and how to bring it back later.

## 1. How to Stash Your Changes
Stashing moves your current modifications and new files into a temporary storage area.

### Step-by-Step
1. **Save everything (including new files):**
   ```bash
   git stash push -u -m "Describe your work here"
   ```
   * *`-u` (or `--include-untracked`) ensures any new files you created are also saved.*
   * *`-m` adds a message so you can identify the stash later.*

2. **Verify it's stashed:**
   ```bash
   git stash list
   ```
   * *This will show a list of all your saved stashes with their IDs (like `stash@{0}`).*

---

## 2. How to Retrieve Your Changes
When you want to bring your work back to your project files.

### Option A: Stash Pop (Recommended)
This brings your changes back and **removes** them from the stash list.
```bash
git stash pop
```

### Option B: Stash Apply
This brings your changes back but **keeps** a copy in the stash list as a backup.
```bash
git stash apply
```
* *If you have multiple stashes, specify the ID:* `git stash apply stash@{0}`

---

## 3. Other Useful Commands

| Command | What it does |
| :--- | :--- |
| `git stash show -p` | See a preview of the actual code changes inside the latest stash. |
| `git stash drop` | Delete the most recent stash permanently. |
| `git stash clear` | **Warning:** Deletes ALL of your stashes permanently! |

---

## Summary Workflow
1. **Work** on your features.
2. **Stash** it away to switch branches or sync with `main`: `git stash push -u -m "My Feature"`
3. **Switch/Sync** your code.
4. **Pop** it back when ready: `git stash pop`
