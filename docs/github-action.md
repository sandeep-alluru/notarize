# GitHub Action

Use notarize directly in your GitHub Actions workflow:

```yaml
- name: notarize
  uses: sandeep-alluru/notarize@v0.1.0
  with:
    # TODO: add action inputs
    fail-on-error: "true"
```

Or use the CLI directly:

```yaml
- name: Install notarize
  run: pip install notarize

- name: Run notarize
  run: notarize --help
```
