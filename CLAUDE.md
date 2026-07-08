# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Repository purpose

Public reference implementation of a `plan → risk-assessment → approval → apply` GitHub Actions pipeline for Terraform, backed by Terraform Cloud. The Terraform target is an Aviatrix AWS spoke + transit fabric, but the workflow itself is provider-agnostic.

- `.github/workflows/workflow-tf-apply-approval.yaml` — the dispatchable pipeline (two jobs: plan+risk-assess, then gated apply).
- `.github/scripts/risk-assess.py` — evaluates `terraform show -json` against `risk-rules.yaml` and writes a Markdown report to `$GITHUB_STEP_SUMMARY`.
- `risk-rules.yaml` — YAML match rules mapping resource changes → severity + rationale.
- `workflow-tf-apply-approval/` — the Terraform root module.

New workflow changes for the approval-gate work should be tagged **enhancement** in the commit subject.

## Workflow shape (`.github/workflows/workflow-tf-apply-approval.yaml`)

Two jobs — preserve this shape when editing:

### `plan` job (renamed at runtime by action)
- Displayed as `Plan and Risk Assessment` or `Destroy Plan and Risk Assessment` depending on `inputs.action`.
- Uses `environment: ${{ inputs.environ }}` (currently `prod`) for secret scoping.
- Runs `terraform plan` (or `plan -destroy`), then `terraform show -json the_plan > plan.json`, then `risk-assess.py` which appends a colored Markdown report to `$GITHUB_STEP_SUMMARY`.
- Uploads `the_plan`, `plan.json`, `plan.out`, `risk-report.md` as an artifact named `tf-plan-${{ github.run_id }}` when `inputs.action` is `plan_apply` or `destroy`.

### `apply` job (gated)
- Displayed as `Apply (gated)` or `Destroy (gated)`; the terraform step renames to `Terraform Destroy` when acting on a `-destroy` plan.
- Guarded by `if: inputs.action == 'plan_apply' || inputs.action == 'destroy'` — skipped for `plan`-only runs.
- Uses `environment: ${{ inputs.environ }}-apply` (currently `prod-apply`). **This is the approval gate** — configure Required reviewers in repo Settings → Environments → `prod-apply`.
- Downloads the plan artifact and runs `terraform apply the_plan`. Because the plan was produced with `-out=the_plan`, this same command performs the destroy when the plan was `-destroy`.

### Required secrets (in both `prod` and `prod-apply` environments)
- `CONTROLLER_ADMIN_PASSWORD` — Aviatrix controller admin password (`TF_VAR_controller_password`)
- `CONTROLLER_IP` — Aviatrix controller IP or hostname (`TF_VAR_controller_ip`)
- `AVIATRIX_ACCOUNT` — Aviatrix cloud access account name (`TF_VAR_aviatrix_account`)
- `TF_CLOUD_ORGANIZATION` — TFC organization; read at `terraform init` time via the env var of the same name, so `providers.tf` doesn't hardcode it
- `TF_API_TOKEN` — TFC user/team token used by `hashicorp/setup-terraform`

The plan job has an early `Verify required secrets` step that fails fast if any of the above are empty (`TF_API_TOKEN` isn't checked because `setup-terraform` will fail loudly on its own).

### Runner + shell notes
- **Runner:** `self-hosted` (an Ubuntu runner with network reach to the Aviatrix controller). Do NOT change to `ubuntu-latest` unless the controller is reachable from GitHub-hosted runners.
- **Default shell:** `bash --noprofile --norc -eo pipefail {0}` — `pipefail` matters: `terraform plan | tee plan.out` would otherwise mask a failing terraform exit with `tee`'s zero exit.
- **Install unzip step** — a fresh Ubuntu runner lacks `unzip`, which `hashicorp/setup-terraform` needs to unzip the CLI archive. Keep this step until the runner image bakes it in.
- **`hashicorp/setup-terraform@v3`** with `terraform_wrapper: false` — the wrapper shims `terraform` through Node, which fails on runners without `node` on PATH. Only `cli_config_credentials_token` is passed; do NOT add `cli_config_credentials_hostname` (TFC uses the default `app.terraform.io`).
- **`actions/checkout@v5`** — v5 uses node24 and silences the node20 deprecation warning. `setup-terraform@v3` still uses node20 upstream; that warning will persist until HashiCorp cuts a new release.

## Risk rules (`risk-rules.yaml`)

Each rule is a `match` block (all fields must match) plus a `level` (`low`/`medium`/`high`/`critical`) and a `reason`. When multiple rules match a single resource change, the **highest** level wins per resource.

`match` fields (all optional; empty match matches every change):
- `action` — one of `create` / `update` / `delete` / `read` / `no-op`
- `resource_type` — Terraform resource type, e.g. `aviatrix_spoke_gateway`
- `resource_address` — full address, e.g. `module.mc-spoke.aviatrix_spoke_gateway.default`
- `attribute_changed` — resource attribute (not module input) whose before/after values differ

**Attribute names must be the underlying Terraform resource attribute, not the module input.** The Aviatrix modules take an `instance_size` variable but the resource attributes are `gw_size` and `ha_gw_size` — rules must match the latter. This has bitten us; check the resource schema before writing a new rule.

The report renders each level with a colored emoji dot (🟢 low, 🟡 medium, 🟠 high, 🔴 critical) followed by the level name. The `top_risk` extraction in the workflow greps for the uppercase level words, so keep them in the icon strings.

## Terraform configuration (`workflow-tf-apply-approval/`)

- `providers.tf`
  - `terraform { cloud { workspaces { name = "43_github_workflow_tf_apply_approval" } } }` — TFC backend. `organization` is intentionally omitted and supplied via `TF_CLOUD_ORGANIZATION` at init time. Hostname is omitted so `app.terraform.io` is used.
  - Aviatrix provider `AviatrixSystems/aviatrix` pinned to `3.2.2`.
  - `provider "aviatrix"` — controller IP from `var.controller_ip`, username hardcoded (`admin`), password from `var.controller_password`. `verify_ssl_certificate = false`.
- `variables.tf` — `controller_password` (sensitive), `controller_ip`, `aviatrix_account`. All populated from `TF_VAR_*` env in the workflow.
- `main.tf` — `module "mc-spoke"` + `module "mc-transit"` (both `terraform-aviatrix-modules/*/aviatrix`), currently in AWS `us-east-1`, spoke attached to transit, `ha_gw = false`, `instance_size = "t3.small"`.
- `43_github_workflow_tf_apply_approval.tfvars` — empty. Exists because `terraform plan -var-file ...` requires it; all variables come from `TF_VAR_*` env.

## TFC workspace settings that matter

- **Execution Mode: Local** — must be set in the TFC UI. If left at the default Remote, TFC runs the plan on its shared cloud runners, which cannot reach the controller.
- Workspace is selected by `name`, so `TF_WORKSPACE` must remain unset (it would conflict at `init`).

## Editing tips

- Adding another workspace target: (1) add to the `workspace` input `options`, (2) create `<name>.tfvars`, (3) create a matching TFC workspace, (4) update `providers.tf` (or switch from `name` to `tags` selector — that decision is not made yet).
- Testing changes: `workflow_dispatch` with `action: plan` — the plan job runs the risk assessment and won't touch the apply gate.
- When you add a new risk rule, dispatch a plan and inspect the run summary to confirm your match landed. Silent misses are common when attribute names differ between module input and resource schema.

## History

The repo was rebuilt from scratch after prior commits contained internal company references. `git init` was done once with a single root commit; there is intentionally no earlier history.
