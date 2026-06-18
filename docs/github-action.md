# GitHub Action

Use tracemarket directly in your GitHub Actions workflow:

```yaml
- name: tracemarket
  uses: sandeep-alluru/tracemarket@v0.1.0
  with:
    # TODO: add action inputs
    fail-on-error: "true"
```

Or use the CLI directly:

```yaml
- name: Install tracemarket
  run: pip install tracemarket

- name: Run tracemarket
  run: tracemarket --help
```
