# Security policy

## Supported versions

Security fixes are applied to the latest release and current `main` while v1 is being prepared. Older beta builds may contain known downloader, filesystem, or lifecycle defects and should not be treated as supported.

## Security model

PromptSmith-cli is a local terminal application. It opens no listening ports and does not require cloud inference credentials.

The main trust boundaries are:

- local user input and files
- downloaded GGUF models
- HTTPS redirects and model-host responses
- clipboard and exported files
- local SQLite history and logs

Run PromptSmith as a normal user. Administrator or root privileges are neither required nor recommended.

## Local data

Prompt history stores full prompts and refined outputs in plaintext SQLite. Session and history exports also contain full content. There is no automatic retention or encryption.

Protect the PromptSmith user-data directory with normal operating-system account permissions. Do not place its history database, logs, or exports in a public synchronization folder unless that exposure is intentional.

Prompt text and refined output must not be written to application logs. When reporting a defect, inspect and sanitize logs, exported history, screenshots, paths, usernames, domains, and model filenames before publishing them.

## Model downloads

Built-in presets are downloaded through HTTPS with:

- URL and redirect validation
- destination-path confinement
- symlink rejection
- streamed writes
- partial-file cleanup
- retry handling
- GGUF-header validation
- known SHA-256 verification
- `fsync` and atomic promotion

Custom model URLs must use HTTPS. A custom model without a supplied checksum receives format validation but not cryptographic identity verification. Only use models from publishers you trust.

Downloaded models are data consumed by native inference code. Treat arbitrary GGUF files as untrusted inputs and keep `llama-cpp-python` current within the versions supported by PromptSmith.

## Network and credentials

PromptSmith does not need API keys. Never embed credentials, private tokens, or production secrets in profiles, templates, screenshots, issue reports, or example prompts.

Outbound network access is used for installation and model downloads. Prompt analysis and local refinement run offline after dependencies and a model are present.

## Reporting a vulnerability

Report vulnerabilities privately to the repository owner rather than opening a public issue containing exploit details or sensitive artifacts. Include:

- affected version or commit
- operating system and Python version
- minimal reproduction
- expected and observed behavior
- security impact
- sanitized logs or traces

Do not include real prompts, credentials, private model URLs, or user data.

## Disclosure expectations

A report will be assessed for reproducibility and impact. Confirmed issues should receive a fix, regression coverage, documentation updates, and a release note before public disclosure when practical.