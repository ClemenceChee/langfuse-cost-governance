# Security Policy

## Reporting a vulnerability

Please do **not** open a public issue for security vulnerabilities. Use GitHub's
private vulnerability reporting instead: go to the repository's **Security** tab
and choose **Report a vulnerability**
([direct link](https://github.com/ClemenceChee/langfuse-cost-governance/security/advisories/new)).
That opens a private advisory visible only to you and the maintainers.

Expect an acknowledgement within a few business days. Please include the
affected version or commit, the deployment topology you are running (see
[docs/topologies.md](docs/topologies.md)), and steps to reproduce.

## Deployment expectations

This stack is designed to run on your own machine or inside your own network.
The API has **no built-in authentication** and Compose binds every published
port to `127.0.0.1` by default (`BIND_HOST`). Exposing it more widely without
an authenticating proxy in front makes every KPI route readable by anyone who
can reach the port, including per-user spend attributed to teams and
departments. Adding an optional auth layer is tracked in
[issue #6](https://github.com/ClemenceChee/langfuse-cost-governance/issues/6).

## Handling Langfuse credentials

This project reads Langfuse API keys (`LANGFUSE_PUBLIC_KEY` /
`LANGFUSE_SECRET_KEY`, or the equivalent fields in `LANGFUSE_PROJECTS`) and
warehouse credentials from `DATABASE_URL`. Never commit these values:

- `.env` is gitignored — copy `.env.example` and edit your copy.
- Use a secret manager (e.g. Docker secrets, HashiCorp Vault, AWS Secrets
  Manager, or your CI provider's encrypted variables) in production.
- The shipped `docker-compose.yml` uses development-only credentials
  (`analytics:analytics`); change them before any non-local deployment.

## Data sensitivity

Langfuse traces can contain prompts, completions, and metadata that may be
confidential or include PII. Treat the analytics warehouse (`fact_observation`)
with the same data-protection controls as your Langfuse instance (encryption at
rest, access control, retention policy).
