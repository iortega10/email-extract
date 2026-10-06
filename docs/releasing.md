# Releasing to PyPI

`.github/workflows/release.yml` publishes `email-extract` with PyPI **Trusted Publishing**, so no
API token is stored anywhere. A PyPI release is permanent and public, and a version number can never
be reused.

The release workflow tags `v*`, runs the suite on Python 3.11 and 3.14, runs the oracle and the three
ledger `--check` tools, builds the sdist and the wheel, runs `twine check`, refuses a tag that does not
equal `pyproject.toml`'s `version`, and then publishes. A tag containing `rc` goes to **TestPyPI**;
anything else goes to **PyPI**.

**Before the first release (yours to settle, not the code's):** confirm ownership of the work with
your employer in writing, and publish from a personal PyPI account.

## One-time setup

1. Accounts on pypi.org and test.pypi.org with 2FA.
2. On each site add a *pending publisher* for `email-extract`:
   * owner: `iortega10`
   * repository: `email-extract`
   * workflow: `release.yml`
   * environment: `pypi` (PyPI) or `testpypi` (TestPyPI)
3. In the GitHub repository create the environments `pypi` and `testpypi`
   (Settings -> Environments).
4. Make the repository public when ready (the project URLs point at it).

## Each release

0. Confirm the working tree is clean and green: `python -m pytest -q` on 3.11 and 3.14,
   `python -m emailextract.evals`, and the three `--check` tools.
1. Set `version` in `pyproject.toml` to the exact version you will tag (`0.1.0rc1` for the dry run,
   `0.1.0` for the real one); the workflow refuses a tag that does not match.
2. Dry run: tag `v0.1.0rc1` -> TestPyPI. In a clean virtualenv:

   ```sh
   pip install --index-url https://test.pypi.org/simple/ \
       --extra-index-url https://pypi.org/simple/ email-extract==0.1.0rc1
   python -c "import emailextract; print(emailextract.__version__)"
   ```

3. Real release: set `0.1.0`, tag `v0.1.0` -> PyPI. Verify with a fresh `pip install email-extract`.

## Verification commands

```sh
python -m pytest -q                                   # green on both interpreters
python -m emailextract.evals                          # the oracle and the gates
python tools/update_behavior_ledger.py --check        # behaviour fingerprints unmoved
python tools/update_label_ledger.py --check           # additions-only label ledger
python tools/make_fixtures.py --check                 # the generated corpus reproduces
python -m build && python -m twine check dist/*       # the sdist and the wheel
```

`python -m build` needs a fresh environment with `build` and `twine` installed
(`python -m pip install build twine`). The wheel carries only `emailextract/**`, its metadata and
`LICENSE`/`NOTICE`; the sdist adds `README.md`, `CHANGELOG.md` and `MANIFEST.in`, and ships **no**
tests, fixtures or docs.
