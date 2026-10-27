# Installation Guide

## Server Requirements

- **OS**: Ubuntu/Debian
- **Docker**: Docker and Docker Compose 2.20.0+ installed
- **RAM**: 512 MB minimum
- **CPU**: 1 CPU core minimum

### ARM64 and Multi-Platform Images

Released images support both `linux/amd64` and `linux/arm64`. Docker selects the
matching image automatically when pulling a release from GHCR, so deployment on
an ARM64 server uses the same `DOCKER_IMAGE` value as an AMD64 server.

## Service Installation

### Prepare service

Before running the remote commands, create `/opt/code-agent/bin` on the server
and manually copy these files from the chosen release checkout:

| Repository file | Server path |
| --- | --- |
| `etc/docker-compose.yml` | `/opt/code-agent/docker-compose.yml` |
| `etc/bin/*` | `/opt/code-agent/bin/` |
| `etc/nginx.conf` | `/opt/code-agent/nginx.conf` |
| `etc/code-agent.service` | `/opt/code-agent/code-agent.service` |
| `.env.template` | `/opt/code-agent/.env.template` |

The unit file must be copied during first installation; CI does not deliver it.
In its `[Service]` section, add `WorkingDirectory=/opt/code-agent` so `bin/stop`
can find the Compose file.

```shell
export TARGET_SERVER="remote-server-ip"
ssh "${TARGET_SERVER}"

# on the remote server
sudo su

export TARGET_DIR="/opt/code-agent"

# prepare user and group (UID/GID 1007 match the container)
groupadd --system code-agent-srv --gid 1007
useradd --no-log-init --system --gid code-agent-srv --uid 1007 code-agent-srv

mkdir -p "${TARGET_DIR}/bin"
# replace RELEASE_TAG with the published image tag matching the copied files
printf 'DOCKER_IMAGE=ghcr.io/dmitryburnaev/code-agent:RELEASE_TAG\n' > "${TARGET_DIR}/.version"
chown -R code-agent-srv:code-agent-srv "${TARGET_DIR}"
usermod -a -G docker code-agent-srv
find "${TARGET_DIR}" -type d -exec chmod 2770 {} +
chmod 660 "${TARGET_DIR}/docker-compose.yml" "${TARGET_DIR}/nginx.conf" "${TARGET_DIR}/code-agent.service" "${TARGET_DIR}/.env.template" "${TARGET_DIR}/.version"
chmod 770 "${TARGET_DIR}"/bin/*

# make env-file
cp "${TARGET_DIR}/.env.template" "${TARGET_DIR}/.env"
chown code-agent-srv:code-agent-srv "${TARGET_DIR}/.env"
# set the secrets and storage mode described below before starting the service:
nano "${TARGET_DIR}/.env"
# only the service account can read/write secrets
chmod 600 "${TARGET_DIR}/.env"

# copy config to systemd
ln -s "${TARGET_DIR}/code-agent.service" /etc/systemd/system/code-agent.service
systemctl daemon-reload
systemctl enable code-agent.service
systemctl start code-agent.service

# see status and logs
systemctl status code-agent.service
journalctl -u code-agent
```

Before starting the service, set `APP_SECRET_KEY`, `VENDOR_ENCRYPTION_KEY`,
`DB_PASSWORD` and `ADMIN_PASSWORD` to secure values in `.env` (for example,
generate each with `openssl rand -hex 32`). The entrypoint also requires
`DB_USER` and `DB_NAME`.

Choose the storage mode in `.env`:

| Setting | Local storage | External storage |
| --- | --- | --- |
| `COMPOSE_PROFILES` | `local-storage` (template default) | empty (`COMPOSE_PROFILES=`) |
| `DB_HOST` | `db` (Compose default) | reachable PostgreSQL hostname |
| `DB_PORT` | `5432` | external server port |
| `DB_USER`, `DB_NAME`, `DB_PASSWORD` | local database credentials | existing database credentials |

The `local-storage` profile currently starts PostgreSQL and can include other
storage services later. Without it, only the app starts. For an external DB,
create the database first: the entrypoint runs migrations immediately. Existing
installations using bundled PostgreSQL must add `COMPOSE_PROFILES=local-storage`
before updating. Stop with the old profile before changing storage mode.

### Setup for deployment

Note: we assume that deployment actions will be performed as the `deploy` SSH user

1. Create the "deploy" user if absent (`adduser deploy`) and configure its CI SSH key.
2. Allow access to service's group (to make changes in specific directories)
   ```shell
   usermod -a -G code-agent-srv,docker deploy
   ```
3. Allow "deploy" user manipulate with code-agent's service
   ```shell
   visudo -f /etc/sudoers.d/deploy
   # add these lines:
   deploy ALL = NOPASSWD: /bin/systemctl restart code-agent.service
   deploy ALL = NOPASSWD: /bin/systemctl show -p ActiveState --value code-agent
   ```
4. Start a new login session after changing groups. Provide `SSH_HOST`, `SSH_PORT`,
   `SSH_USER`, `SSH_PKEY` and `PROD_PROJECT_ROOT=/opt/code-agent` to CI
   (see `.github/workflows/deploy.yaml`).

Release publication is automatic; deployment is manual. After the release is
published, open **Actions → Deploy → Run workflow** and enter its tag (for example,
`1.2.3`). The workflow deploys the image and configuration from that tag.

These sudoers entries cover CI restart/status only. Run the full `bin/service`
helper from an administrator account for start/stop, status and journal access.

## Service Management

The application includes a convenient service management script located at `bin/service` on the server. This script provides easy access to common service operations.

### Using the Service Script

```bash
# Basic commands
bin/service start          # Start the service
bin/service stop           # Stop the service  
bin/service restart        # Restart the service
bin/service status         # Show service status
bin/service health         # Check service health

# View logs
bin/service logs                    # Show recent logs (last 50 lines)
bin/service logs --tail 100         # Show last 100 lines
bin/service logs --follow           # Follow logs in real-time
bin/service logs --grep error       # Filter logs by pattern
bin/service logs --since "1 hour ago"  # Show logs since specific time

# Start/restart with log following
bin/service start --logs            # Start and follow logs
bin/service restart --logs          # Restart and follow logs
```

### Service Script Features

- **Health checks**: Verify service status and check for recent errors
- **Flexible logging**: Filter logs by time, pattern, or follow in real-time
- **Easy management**: Simple commands for start/stop/restart operations
- **Error detection**: Automatic detection of service issues

### Nginx Configuration as a Reverse Proxy

The service requires Nginx as a reverse proxy to handle:
- Domain-based routing (code.example.com)
- Security layer (authorization header check)
- API endpoint protection (only /api/* endpoints are accessible)

**Important**: The application runs in a container via uvicorn with specific flags for proper reverse proxy interaction:
- `--proxy-headers`: Enables processing of proxy headers (X-Forwarded-For, X-Forwarded-Proto, etc.)
- `--forwarded-allow-ips`: Allows trusted proxy IPs to set forwarded headers

These flags are essential for correct client IP detection and protocol handling when behind Nginx.

To configure Nginx:

1. Copy the configuration file from `etc/nginx.conf` to your Nginx configuration directory:
   ```bash
   sudo cp "${TARGET_DIR}/nginx.conf" /etc/nginx/sites-available/code-agent.conf
   ```

2. Create a symbolic link to enable the site:
   ```bash
   sudo ln -s /etc/nginx/sites-available/code-agent.conf /etc/nginx/sites-enabled/
   ```

3. Update the configuration:
   ```bash
   sudo nano /etc/nginx/sites-available/code-agent.conf
   ```
   - Replace `code.example.com` with your domain
   - Set the `backend_app` upstream to `127.0.0.1:8003` to match the default `APP_PORT=8003` (the example currently uses port `8000`)
   - Ensure the `Authorization` header is properly set in all API requests

4. Test and reload Nginx:
   ```bash
   sudo nginx -t
   sudo nginx -s reload
   ```

5. Set up HTTPS with Certbot (recommended):
   ```bash
   # Install Certbot and Nginx plugin
   sudo apt update
   sudo apt install certbot python3-certbot-nginx
   
   # Obtain and install SSL certificate
   sudo certbot --nginx -d code.example.com
   
   # Verify auto-renewal is enabled
   sudo systemctl status certbot.timer
   ```

After running Certbot, it will:
- Automatically modify your Nginx configuration to handle HTTPS
- Set up automatic certificate renewal (every 90 days)
- Configure secure SSL settings
- Optionally redirect all HTTP traffic to HTTPS (recommended)

Note: Make sure your domain's DNS records are properly configured and pointing to your server before running Certbot.
