# System Info API

A simple FastAPI application that provides system information and health check endpoints.

## Prerequisites

- Docker and Docker Compose
- Python 3.13 (for local development)
- uv package manager

## Service Installation

### Upload config files
```shell
TARGET_SERVER="remote-server-ip"
TARGET_DIR="/opt/code-agent"
ssh ${TARGET_SERVER} -C  "mkdir -P ${TARGET_DIR}"
scp -r etc/* ${TARGET_SERVER}:${TARGET_DIR}
```

### Prepare service
```shell
ssh ${TARGET_SERVER}

# on the remote server
sudo su

export TARGET_SERVER="remote-server-ip"
export TARGET_DIR="/opt/code-agent"

# prepare user and group (NOTE: ID 1005 is imported ID for group)
groupadd --system code-agent-srv --gid 1007
useradd --no-log-init --system --gid code-agent-srv --uid 1007 code-agent-srv

chown code-agent-srv:code-agent-srv -R /opt/code-agent/
usermod -a -G docker code-agent-srv
chmod -R 660 /opt/code-agent # all files can be rewritable by code-agent-srv group
chmod -R ug+x /opt/code-agent/bin # code-agent-srv group can execute bin files (for service running)
chmod ug+x /opt/code-agent # code-agent-srv group can execute bin files (for service running)

# copy config to systemd
ln -s ${TARGET_DIR}/code-agent.service /etc/systemd/system/code-agent.service
systemctl daemon-reload
systemctl enable code-agent.service
systemctl start code-agent.service

# see status and logs
systemctl status code-agent.service
journalctl -u code-agent
```
### Prepare for deployment
1. Prepare "deploy" user
2. Allow access to service's group (to make changes in specific directories)
   ```shell
   usermod -a -G code-agent-srv deploy
   ```
3. Allow "deploy" user manipulate with code-agent's service
   ```shell
   visudo -f /etc/sudoers.d/deploy
   # add these lines:
   deploy ALL = NOPASSWD: /bin/systemctl restart code-agent.service
   deploy ALL = NOPASSWD: /bin/systemctl show -p ActiveState --value code-agent
   ```

### Nginx Configuration

The service requires Nginx as a reverse proxy to handle:
- Domain-based routing (code.example.com)
- Security layer (authorization header check)
- API endpoint protection (only /api/* endpoints are accessible)

To configure Nginx:

1. Copy the configuration file from `etc/nginx.conf` to your Nginx configuration directory:
   ```bash
   sudo cp etc/nginx.conf /etc/nginx/sites-available/code-agent
   ```

2. Create a symbolic link to enable the site:
   ```bash
   sudo ln -s /etc/nginx/sites-available/code-agent /etc/nginx/sites-enabled/
   ```

3. Update the configuration:
   - Replace `code.example.com` with your domain
   - Update the port in `proxy_pass` directive to match your application port
   - Ensure the `Authorization` header is properly set in all API requests

4. Test and reload Nginx:
   ```bash
   sudo nginx -t
   sudo systemctl reload nginx
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

## Development

1. Install venv
    ```shell
    make install
    ```
2. Format changes
   ```shell
   make format
   ```
3. Lint changes 
   ```shell
   make lint
   ```
4. Run tests 
   ```shell
   make test
   ```

## Swagger Documentation

When enabled, the Swagger documentation is available at `/docs` and ReDoc at `/redoc`.

## Environment Variables

| Variable Name   | Description                                | Default Value          |
|-----------------|--------------------------------------------|------------------------|
| LOG_LEVEL       | Sets the logging level for the application | INFO                   |
| AUTH_API_TOKEN  | API token for authentication               | (required, no default) |
| PROVIDERS       | List of providers in JSON format           | []                     |
| SWAGGER_ENABLED | Enables/disables Swagger documentation     | true                   |
| APP_HOST        | Host address for the application           | localhost              |
| APP_PORT        | Port number for the application            | 8003                   |
