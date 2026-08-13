# CI/CD setup (GitHub Actions → Lightsail, via OIDC + SSM)

No static AWS keys stored in GitHub — the workflow assumes an IAM role via OIDC, then tells the server to redeploy itself via AWS Systems Manager (SSM) Run Command. I can't do any of this from here (all AWS console/CLI), but it's a one-time setup — once done, every push to `main` deploys automatically.

**Important:** Lightsail instances aren't natively SSM-managed like EC2 is. This needs a one-time **SSM hybrid activation** on the box first (step 3 below) - that's the part with the most moving pieces.

---

## 1. Create the GitHub OIDC identity provider (if not already present)

IAM console → **Identity providers** → check if `token.actions.githubusercontent.com` already exists (common if you've done this for another repo). If not:
- **Add provider** → Provider type: **OpenID Connect**
- Provider URL: `https://token.actions.githubusercontent.com`
- Audience: `sts.amazonaws.com`
- Create

## 2. Create the IAM role GitHub Actions will assume

IAM console → **Roles** → **Create role** → **Web identity**:
- Identity provider: the one from step 1
- Audience: `sts.amazonaws.com`
- Trust policy - after creating, edit it to scope to this exact repo/branch (replace `<AWS_ACCOUNT_ID>` and the repo path):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<AWS_ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:abheeshkumaran/Natsukashi_Main:ref:refs/heads/main"
        }
      }
    }
  ]
}
```

- Name it e.g. `github-actions-deploy-natsukashi`
- Attach a permissions policy (create a new one, don't use a broad managed policy) scoped to just what's needed:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ssm:SendCommand",
        "ssm:GetCommandInvocation"
      ],
      "Resource": [
        "arn:aws:ssm:<REGION>::document/AWS-RunShellScript",
        "arn:aws:ssm:<REGION>:<AWS_ACCOUNT_ID>:managed-instance/*"
      ]
    }
  ]
}
```

- Note the role's ARN once created (`arn:aws:iam::<AWS_ACCOUNT_ID>:role/github-actions-deploy-natsukashi`)

## 3. Register the Lightsail instance with SSM (hybrid activation)

**3a. Create an IAM role for the hybrid instance** (separate from the role above - this one is assumed by the SSM agent running on the box, not by GitHub):
- IAM console → Roles → Create role → **AWS service** → use case doesn't fit the default hybrid setup wizard well from Lightsail, so create it manually:
  - Trusted entity: custom trust policy:
    ```json
    {
      "Version": "2012-10-17",
      "Statement": [{
        "Effect": "Allow",
        "Principal": { "Service": "ssm.amazonaws.com" },
        "Action": "sts:AssumeRole"
      }]
    }
    ```
  - Attach policy: `AmazonSSMManagedInstanceCore`
  - Name it e.g. `ssm-hybrid-natsukashi`

**3b. Create the activation** (from your machine, with AWS CLI configured with an admin/your own credentials - this is separate from the GitHub role):
```bash
aws ssm create-activation \
  --iam-role ssm-hybrid-natsukashi \
  --registration-limit 1 \
  --region ap-south-1
```
This prints an `ActivationCode` and `ActivationId` - copy both, the code is only shown once.

**3c. Install and register the SSM agent on the Lightsail instance:**
```bash
# On the Lightsail server:
sudo snap install amazon-ssm-agent --classic
sudo snap stop amazon-ssm-agent

sudo amazon-ssm-agent -register \
  -code "<ActivationCode>" \
  -id "<ActivationId>" \
  -region "ap-south-1"

sudo snap start amazon-ssm-agent
```

**3d. Find the resulting Managed Instance ID:**
- AWS console → Systems Manager → **Fleet Manager** → look for an instance with a `mi-...` ID (not `i-...`, that prefix means EC2) with the Lightsail instance's hostname
- That `mi-...` value is what goes in the GitHub repo variable below

## 4. Set GitHub repo variables (not secrets - none of these are sensitive on their own)

Repo → **Settings → Secrets and variables → Actions → Variables** tab → **New repository variable**, add:
- `AWS_DEPLOY_ROLE_ARN` = the role ARN from step 2
- `AWS_REGION` = `ap-south-1`
- `SSM_INSTANCE_ID` = the `mi-...` ID from step 3d

## 5. Test it

Push any small change to `main`, or manually trigger via **Actions** tab → **Deploy to Lightsail** → **Run workflow**. Watch the run's logs - it streams `deploy.sh`'s full output (stdout + stderr) directly into the GitHub Actions log.

## Ongoing

- `deploy/deploy.sh` is the actual script that runs on the server each deploy - it only reinstalls dependencies/collects static when those specific files changed (keeps routine deploys fast), always runs migrations (safe/fast no-op when nothing's pending), restarts PM2 with `--update-env`, and fails loudly (non-zero exit, printing the last 30 lines of the error log) if the app isn't back up and responding after restart - so a broken deploy shows as a failed GitHub Actions run, not a silent 502 you find out about later.
- Every run also appends to `deploy/deploy.log` on the server itself, so `tail -f deploy/deploy.log` while a deploy is running (or reviewing it after) works independent of GitHub's UI.
- To add a new IAM permission or change what the workflow can do, edit the permissions policy from step 2 - the workflow itself never needs new secrets for that, since it's all scoped through the role.
