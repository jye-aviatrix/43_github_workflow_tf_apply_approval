# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Repository purpose

This repo contains one GitHub Actions workflow plus the Terraform source it drives:

- `.github/workflows/workflow-tf-apply-approval.yaml` — dispatchable pipeline that runs `terraform plan` / `apply` / `destroy`.
- `workflow-tf-apply-approval/` — the Terraform root module (Aviatrix multi-cloud spoke via `terraform-aviatrix-modules/mc-spoke/aviatrix`). State is stored in **Terraform Cloud** (`app.terraform.io`, workspace `43_github_workflow_tf_apply_approval`; org is supplied at runtime via the `TF_CLOUD_ORGANIZATION` env var).

The repo's name refers to a plan → risk-assessment → approval → apply gate that is being introduced. New workflow changes for that gate should be labeled/tagged as **enhancement** — see the section at the bottom of this file.

## Workflow shape (`.github/workflows/workflow-tf-apply-approval.yaml`)

Preserve this shape when editing:

- **Trigger:** `workflow_dispatch` with inputs `action` (`plan`|`apply`|`destroy`, default `plan`), `workspace` (choice — currently only `43_github_workflow_tf_apply_approval`), and `environ` (choice — currently only `prod`).
- **Environment binding:** `environment: ${{ inputs.environ }}` — this binds the run to a GitHub environment for secret scoping. Required secrets in that environment:
  - `CONTROLLER_ADMIN_PASSWORD` (Aviatrix controller admin password)
  - `CONTROLLER_IP` (Aviatrix controller IP or hostname)
  - `AVIATRIX_ACCOUNT` (Aviatrix cloud access account name, passed as `TF_VAR_aviatrix_account`)
  - `TF_CLOUD_ORGANIZATION` (Terraform Cloud org name — read via the `TF_CLOUD_ORGANIZATION` env var at init time so it isn't hardcoded in `providers.tf`)
  - `TF_API_TOKEN` (TFC user/team token used by `setup-terraform`)
- **Runner:** `self-hosted` (an Ubuntu runner with network reach to the Aviatrix controller). Do NOT change to `ubuntu-latest` unless the controller is reachable from GitHub-hosted runners.
- **Default shell:** `bash --noprofile --norc -eo pipefail {0}` — the `pipefail` matters: several steps pipe through `tee`, and without it a failing `terraform` command would be masked by `tee`'s zero exit.
- **TFC workspace selector:** pinned by `name` in `providers.tf`. `TF_WORKSPACE` is deliberately NOT set — it would conflict with the `name` selector at `terraform init`. The `workspace` input is used only to pick the `.tfvars` filename.
- **Step order:** `checkout` → `Verify required secrets` (fail-fast) → `checkip` → `Install unzip` → `Setup Terraform` → `fmt -check` → `init` → `validate` → `plan` (or `plan -destroy`) with `-var-file ${{inputs.workspace}}.tfvars -out=the_plan`, teed to `plan.out` → `apply the_plan` or `destroy -auto-approve`. The `.tfvars` filename must match the `workspace` input.
- **Setup Terraform:** `hashicorp/setup-terraform@v3` with `terraform_wrapper: false` — the wrapper shims `terraform` through Node, which fails on runners without `node` on PATH. Only `cli_config_credentials_token` is passed; do NOT add `cli_config_credentials_hostname` (TFC uses the default `app.terraform.io`).
- **Install unzip step:** `hashicorp/setup-terraform` unzips the CLI archive; a bare Ubuntu runner lacks `unzip`. Keep this step until the runner image bakes it in.
- Commented-out `terraform untaint` scaffolding is kept intentionally — uncomment (don't rewrite) when re-enabling.

## Terraform configuration (`workflow-tf-apply-approval/`)

- `providers.tf`
  - `terraform { cloud { workspaces { name = "43_github_workflow_tf_apply_approval" } } }` — TFC backend. `organization` is intentionally omitted from source and supplied via the `TF_CLOUD_ORGANIZATION` env var at init time. Hostname is also omitted so `app.terraform.io` is used.
  - Aviatrix provider `AviatrixSystems/aviatrix` pinned to `3.2.2`.
  - `provider "aviatrix"` — controller IP from `var.controller_ip`, username (`admin`), password from `var.controller_password`. `verify_ssl_certificate = false` because the controller's cert isn't in the runner's trust store.
- `variables.tf` — declares `controller_password` (sensitive) and `controller_ip`. Both are populated from `TF_VAR_*` env in the workflow, sourced from `secrets.CONTROLLER_ADMIN_PASSWORD` and `secrets.CONTROLLER_IP`.
- `main.tf` — one `module "mc-spoke"` block (`terraform-aviatrix-modules/mc-spoke/aviatrix` v1.7.1) creating an Azure spoke with `attached = false`.
- `43_github_workflow_tf_apply_approval.tfvars` — empty file. Exists because `terraform plan -var-file ...` requires it; all variables currently come from `TF_VAR_*` env.

## TFC workspace settings that matter

- **Execution Mode: Local** — must be set in the TFC UI. If left at the default Remote, TFC runs the plan on its shared cloud runners, which cannot reach the private controller IP.
- Workspace is selected by `name` (not tags), so `TF_WORKSPACE` must remain unset in the workflow.

## Editing tips

- Adding another workspace target means: (1) add to the `workspace` input `options`, (2) create `<name>.tfvars`, (3) create a matching TFC workspace and update `providers.tf` (since `name` is single-valued, multi-workspace routing would require switching to a `tags` selector — that decision is not made yet).
- No local build/lint/test — validation is via `workflow_dispatch` with `action: plan`.

## Upcoming refactor: plan → risk-assessment → approval → apply

We are refactoring the workflow so that `terraform apply` cannot run until:
1. A `terraform plan` has been captured.
2. A risk assessment / review is performed on that plan.
3. A human approval gate passes.

**Any workflow change made for this refactor must be labeled `enhancement`** (PR label / commit tag). Preserve the current step order and env plumbing; add the gate between plan and apply rather than restructuring around it.
