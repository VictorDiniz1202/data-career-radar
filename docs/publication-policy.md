# Publication Policy

This policy applies to the separate implementation repository. The study folder and its planning context are versioned in the private studies repository. Implementation repositories are created outside the studies tree, without nested Git repositories. Personal planning, resumes and application records must not be exported into the implementation repository.

## Include

Source code; tests; small, purpose-built fixtures; migrations and model schemas; dependency manifests and lockfiles; Docker configuration; CI; sanitized environment examples; a concise README; architecture rationale; data acquisition instructions; verified results; and technical incident write-ups reviewed for disclosure.

## Exclude

Internal planning and research, agent prompts, candidate profiles, resumes, application history, credentials, employer material, raw API dumps, database files, logs, caches, notebook outputs, generated build artifacts and backups.

Schema definitions needed to run the software are source artifacts. They must not be excluded merely because an internal document is also named `schema.md`. Public technical documentation must be self-contained and must not depend on ignored private planning files.

## Release Review

1. Inspect tracked files and the staged diff, including paths ignored after they were previously tracked.
2. Verify that examples and screenshots contain no real secrets, personal records or employer information.
3. Run secret detection locally and in CI once the implementation supplies it. A `.gitignore` file alone is not a security control.
4. Verify the data's license and permitted reuse before publishing samples.
5. Reproduce setup and relevant tests from a clean clone.
6. Confirm that README results were actually measured and that limitations are stated.

Ignoring a file does not remove an existing tracked copy or erase history. Keep private context backed up separately. Do not rewrite Git history or remove existing tracked material without reviewing the affected repository.
