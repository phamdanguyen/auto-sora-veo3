---
description: Automates the git push process: checks status, adds files, generates a commit message, and pushes code.
---
1. Run `git status` to see what has changed.
2. Run `git add .` to stage all files.
3. Look at the changes (using `git diff --staged` or by recalling what you just did). Generate a meaningful, conventional commit message based on these changes.
4. Run `git commit -m "YOUR_GENERATED_MESSAGE"`.
5. Run `git push`.
