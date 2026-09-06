# Repository guidance

- Use `fluxyard` for the project/product and `Fluxyard Inc.` for the company.
  Do not rename technical identifiers, paths or the GitHub organization.
- Use `gh-zhentan` for this repository's issues and pull requests. Keep origin
  at `git@github-zhentan:Fluxyard-Inc/images.git`.
- This repository is the canonical source for these image recipes and examples.
  Review changes here. Identify downstream copies by their public source commit;
  do not maintain silently divergent recipe copies.
- Preserve immutable base/model references and wheel hashes. Record the reviewed
  source commit, build inputs and resulting manifest digest together. A local
  image ID or tag is not a published manifest digest or acceptance evidence.
- Do not import private services, credentials, local proof logs, internal tests
  or unrelated Git history. Never read or export ambient credential files.
- Image publication, GPU/privileged checks and deployment require explicit
  approval for their exact targets. Recipe edits alone authorize none of them.
  Keep public-source availability separate from image-layer and license review;
  do not add a project-wide license grant without the owner's decision.
- Use focused local syntax/JSON/copy checks for source-only changes. Obtain
  independent review at the settled source head. Do not add Actions workflows
  or automatic build/publish jobs without an explicit CI cost budget.
