# PFC delivery default

After implementing and validating a requested PFC change, increment the patch
version (for example 0.17.20 -> 0.17.21), regenerate the portable pfc.py, and push
main plus the version tag. Verify the app's Check for Updates source contains the
new version. Also verify the existing private GitLab backup mirror has identical
branch/tag references. Do not create a separate release repository.

Skip versioning/publishing only when the user explicitly says not to. Never
publish unrelated changes, credentials, unvalidated fixes, or claim a failed
mirror is complete. Preserve existing user work and report release blockers.
