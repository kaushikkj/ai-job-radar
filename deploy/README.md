# AI Job Radar production deployment

The GitHub Actions pipeline builds the backend and frontend containers, publishes them to GHCR, deploys the tagged images to a Linux host over SSH, and verifies the backend health endpoint.

## GitHub environment

Create a GitHub environment named `production` and add these secrets:

- `DEPLOY_HOST` — production server hostname or IP
- `DEPLOY_USER` — Linux user used for deployment
- `DEPLOY_SSH_KEY` — private SSH key for that user
- `DEPLOY_PATH` — absolute deployment directory, for example `/opt/ai-job-radar`
- `GHCR_USERNAME` — GitHub username with permission to pull the packages
- `GHCR_TOKEN` — GitHub PAT/classic token with `read:packages`

Add this repository variable:

- `PUBLIC_API_URL` — browser-reachable backend URL, for example `http://SERVER_IP:8000` or your future HTTPS API URL

## One-time server setup

Install Podman and the Podman Compose provider on the Linux server. Create the deployment directory and place the production `.env` there:

```bash
mkdir -p /opt/ai-job-radar
cd /opt/ai-job-radar
nano .env
```

Copy `data/companies.json` to `/opt/ai-job-radar/companies.json` once. The workflow updates `compose.prod.yaml` on every deployment.

The `.env` file must contain production secrets and must never be committed to Git.

## Deployment behavior

Every push to `main` runs tests and builds. A successful `main` push then:

1. Builds backend and frontend images.
2. Pushes SHA and `latest` tags to GHCR.
3. SSHes to the deployment host.
4. Pulls the exact commit SHA images.
5. Restarts only the application containers.
6. Preserves the `radar_data` named volume.
7. Calls `/health` to verify the backend.
