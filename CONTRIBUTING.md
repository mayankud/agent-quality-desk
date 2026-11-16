# Contributing

This is a portfolio prototype prepared by Mayank Udaywal. Issues and discussion are welcome, especially disagreements about how a case should be scored. Pull requests that change scoring are not merged into the frozen Run 5 files, because the value of this result is that it cannot move.

## Ground rules

- **The Run 5 result is frozen.** Files covered by `pipeline/runs/*/lock.json` must stay byte-identical, or `replay.py` fails. Proposals for a fix belong in a new run with a new lock and a fresh holdout.
- **Fix test-first.** Add a fixture that fails on the current code, then change the code.
- **No retuning on seen data.** Holdout v4 and stress v4 have been seen. A change needs fresh cases to show it works.

## Before opening a pull request

```sh
cd pipeline
python3 replay.py
python3 fixtures7.py && python3 test_harness.py && python3 test_evaluate5.py && python3 test_e2e.py
```

All must pass. Python 3.10 or later, standard library only.

## Reporting a problem

Open an issue using the templates. For a scoring disagreement, give the case ID, the check (c1 to c6), the verdict you expected and the evidence record that supports it.
