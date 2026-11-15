# What To Do

## Done means released

- A merge to master always ships together with a release (the `release` skill) in the same task, without a separate command from Max. Master without a release is unfinished work.
- Everything is verified before master: in the branch, on a copy of the data, with your own eyes on the screen. Only what goes straight into a release gets into master.
- Say "done" and "rolled out" only after the release is published. The report includes the version number and a link to the release.
- Max updates his own copy himself with the **Update to X.Y.Z** button in the app; remind him to.

## Language

- The interface, messages, code comments and docs are English; tests/test_english_only.py fails on any Russian letter outside user data and prompts. User data and prompts stay in the user's language.
