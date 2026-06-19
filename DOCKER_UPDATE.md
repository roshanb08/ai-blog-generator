# Updating the Docker Image

This guide covers how to pull a newer version of the AI Blog Generator image and apply it to your running setup — with zero data loss.

---

## Check your current version

```bash
docker inspect ai-blog-generator \
  --format '{{index .Config.Image}}'
```

Or check the container labels:

```bash
docker inspect ai-blog-generator \
  --format '{{index .Config.Labels "org.opencontainers.image.version"}}'
```

---

## Available tags

| Tag | Description |
|-----|-------------|
| `1.0.0` | Stable release — pin this in production |
| `latest` | Always the most recent build from `main` |

Browse all published versions:

```
https://github.com/{username}/ai-blog-generator/pkgs/container/ai-blog-generator
```

---

## Option A — Docker run

### 1. Pull the new image

```bash
docker pull ghcr.io/{username}/ai-blog-generator:latest
```

To pin a specific version:

```bash
docker pull ghcr.io/{username}/ai-blog-generator:1.1.0
```

### 2. Stop and remove the current container

Your data is safe — it lives in the `ai_blog_data` named volume, not in the container.

```bash
docker stop ai-blog-generator
docker rm ai-blog-generator
```

### 3. Start a new container with the updated image

```bash
docker run -d \
  --name ai-blog-generator \
  --env-file .env \
  -p 8000:8000 \
  -v ai_blog_data:/data \
  --restart unless-stopped \
  ghcr.io/{username}/ai-blog-generator:latest
```

### 4. Verify

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

---

## Option B — Docker Compose

### 1. Update the image tag in `docker-compose.yml`

```yaml
services:
  api:
    image: ghcr.io/{username}/ai-blog-generator:latest  # change tag here
```

### 2. Pull and restart

```bash
docker compose pull
docker compose up -d
```

Compose automatically replaces the old container and reconnects the existing volume.

### 3. Verify

```bash
curl http://localhost:8000/health
# {"status":"ok"}

docker compose logs --tail 20
```

---

## Clean up old images

After updating, the old image stays on disk. Remove it to free space:

```bash
# Remove dangling images (untagged layers from old builds)
docker image prune -f

# Or remove a specific old version explicitly
docker rmi ghcr.io/{username}/ai-blog-generator:1.0.0
```

---

## Rollback

If the new version has an issue, roll back by pointing to the previous tag:

**Docker run:**

```bash
docker stop ai-blog-generator && docker rm ai-blog-generator

docker run -d \
  --name ai-blog-generator \
  --env-file .env \
  -p 8000:8000 \
  -v ai_blog_data:/data \
  --restart unless-stopped \
  ghcr.io/{username}/ai-blog-generator:1.0.0
```

**Docker Compose** — revert the tag in `docker-compose.yml`, then:

```bash
docker compose up -d
```

> The deduplication database in `ai_blog_data` is forward- and backward-compatible across patch and minor versions.
