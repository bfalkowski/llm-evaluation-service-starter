# Security Scanning

The CI pipeline includes a `Security checks` job for fast supply-chain feedback.

Current checks:

- `pip-audit` scans the installed Python dependency graph for known vulnerabilities.
- `scripts/validate_dockerfile_policy.py` enforces a small Dockerfile policy for this
  starter: no `latest` base image tag, non-root runtime user, `--no-cache-dir` package
  installs, and exec-form `CMD`.

The checks are intentionally local and deterministic enough for pull requests. They do
not require a vulnerability management account, cloud provider, private registry, or
cluster access.

## Container Image Scanning

Managed deployments should scan the published image in the registry or deployment
pipeline before promotion. Keep that scanner pinned and reviewed like any other
supply-chain dependency.

A production-shaped flow usually looks like:

```text
build image
publish immutable SHA tag
scan image by digest
review high/critical findings
promote digest into environment values
```

Do not fail production deployments on every low-severity finding by default. Track
severity, exploitability, package reachability, and whether a fixed base image or
library version is available.

## Finding Handling

When a scan fails:

1. Confirm whether the affected package is direct or transitive.
2. Check whether a fixed version exists.
3. Prefer dependency or base-image upgrades over ignores.
4. Document temporary ignores with a reason, expiration, and issue link.
5. Re-run CI before publishing a new image.
