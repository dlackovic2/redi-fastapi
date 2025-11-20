# REDI - Fast Diacritic Restoration API

⚡ Fast diacritic restoration API service for Croatian, Slovenian, and Serbian names and text.

This is a modernized fork of the original [REDI](https://github.com/clarinsi/redi) project, rewritten from Python 2.7 to Python 3 and packaged as a standalone FastAPI microservice with preloaded models for instant responses.

[![Python 3.14](https://img.shields.io/badge/python-3.14-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.121+-green.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## Features

- 🚀 **Smart Caching**: Croatian preloaded, other languages loaded on-demand
- 🔒 **Rate Limiting**: Per-IP protection
- 💾 **Memory Efficient**: ~750 MB baseline, up to 1.9 GB with all languages cached
- ⚡ **High Performance**: 900+ req/s throughput when models are cached on localhost
- 🐳 **Docker Ready**: Production-ready containerized deployment
- 🏥 **Health Monitoring**: Built-in health checks
- 🧹 **Auto Cleanup**: Automatic memory management with periodic garbage collection
- 📚 **Interactive API docs** - Swagger UI and ReDoc included

## 💡 Use Case

Perfect for web applications where users enter names without diacritics:

```
Input:  "Zeljko"  →  Suggestion: "Željko?"
Input:  "Sasa"    →  Suggestion: "Saša?"
Input:  "Zoran"   →  No suggestion (already correct)
```

## Quick Start

### Using Docker (Recommended)

```bash
# Build image
docker compose build

# Start service
docker compose up -d

# Check logs
docker compose logs -f

# Test
curl http://localhost:8002/health
```

### Local Development

```bash
# Clone repository

git clone https://github.com/dlackovic2/redi-fastapi.git
cd redi-fastapi

# Create virtual environment

python -m venv venv
source venv/bin/activate  \# On Windows: venv\Scripts\activate

# Install dependencies

pip install -r requirements.txt

# Ensure models directory exists with .tm files

ls models/

# Should contain: wikitweetweb.hr.tm, wikitweetweb.sl.tm, wikitweetweb.sr.tm

# Run the service
uvicorn main:app --reload --host 0.0.0.0 --port 8001

```

## 📚 API Documentation

Once running, interactive documentation is available at:

- **Swagger UI**: <http://localhost:8001/docs>
- **ReDoc**: <http://localhost:8001/redoc>
- **OpenAPI JSON**: <http://localhost:8001/openapi.json>

## API Endpoints

### `POST /suggest`

Suggest diacritic correction for a name.

**Request:**

```json
{
  "name": "Srecko",
  "lang": "hr"
}
```

**Response:**

```json
{
  "original": "Srecko",
  "suggestion": "Srećko",
}
```

### `GET /health`

Health check endpoint. Returns HTTP 200 if Croatian model is loaded and service is healthy, HTTP 503 otherwise.

**Response:**

```json
{
  "status": "healthy",
  "loaded_languages": ["hr"],
  "required_loaded": true,
  "stats": {
    "loaded": ["hr"],
    "request_counts": {"hr": 42},
    "last_used": {"hr": 5}
  }
}
```

### `GET /stats`

Cache statistics.

**Response:**

```json
{
  "loaded": ["hr"],
  "request_counts": {"hr": 42, "sl": 5},
  "last_used": {"hr": 2, "sl": 310}
}
```

## 💻 Integration Examples

### JavaScript/TypeScript

```Javascript
async function checkDiacritics(name, lang = 'hr') {
    const response = await fetch('http://localhost:8001/suggest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, lang })
    });

    const data = await response.json();

    if (data.suggestion) {
        // Show suggestion to user
        showNotification(data.suggestion);
    }

    return data;
}

// Example: Form validation
document.getElementById('nameInput').addEventListener('blur', async (e) => {
    const result = await checkDiacritics(e.target.value);
    if (result.suggestion) {
        showSuggestionPopup(result.suggestion);
    }
});

```

### Python (Requests)

```python
import requests

def suggest_diacritics(name, lang='hr'):
    response = requests.post(
        'http://localhost:8001/suggest',
        json={'name': name, 'lang': lang},
        timeout=2
    )
    return response.json()

# Usage

result = suggest_diacritics('Zeljko')
if result['suggestion']:
    print(result['suggestion'])  \# "Did you mean Željko?"

```

### cURL

```bash
# Suggest

curl -X POST http://localhost:8001/suggest \
-H "Content-Type: application/json" \
-d '{"name": "Sasa", "lang": "hr"}'

```

## Smart Caching Behavior

### Memory Usage

```
Startup:           ~750 MB (Croatian preloaded)
+ Slovenian:       ~1.3 GB (temporary spike during load)
+ Serbian:         ~1.9 GB (temporary spike during load)
After cleanup:     ~750 MB (back to baseline)
```

### Language Loading Strategy

1. **Croatian (hr)**: Always preloaded and kept in memory
2. **Slovenian/Serbian**: Loaded on first request
3. **Caching**: Languages stay cached while actively used
4. **Auto-unload**: Unused languages unloaded after 30 seconds of inactivity
5. **Concurrent Protection**: Maximum 2 languages loading simultaneously

## Rate Limiting

Protection against abuse with per-IP rate limits:

- **Croatian**: 10 requests/minute per IP
- **Slovenian/Serbian**: 5 requests/minute per IP
- **Window**: 60 seconds rolling window

## Deployment

### GitHub Container Registry

```bash
# Build and tag
docker build -t redi-api:latest .
docker tag redi-api:latest ghcr.io/YOUR_USERNAME/redi-api:latest

# Login to GHCR
echo "YOUR_GITHUB_TOKEN" | docker login ghcr.io -u YOUR_USERNAME --password-stdin

# Push
docker push ghcr.io/YOUR_USERNAME/redi-api:latest
```

### Production Server

```bash
# Pull image
docker pull ghcr.io/YOUR_USERNAME/redi-api:latest

# Deploy
cd /var/www/redi-api
docker compose up -d

# Check logs
docker compose logs -f

# Verify
curl http://localhost:8002/health
```

### Nginx Configuration

```nginx
upstream redi_backend {
    server 127.0.0.1:8002;
    keepalive 32;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    # SSL configuration...
    
    location /redi/ {
        rewrite ^/redi/(.*) /$1 break;
        proxy_pass http://redi_backend;
        
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_connect_timeout 5s;
        proxy_read_timeout 10s;
    }
}
```

## Maintenance

### Daily Restart

Due to Python memory fragmentation from frequent model loading/unloading, a daily restart is already implemented with Alpine cronjob in Docker Compose.

### Manual Cleanup

```bash
# Restart service
docker compose restart

# Full cleanup
docker compose down
docker system prune -f
docker compose up -d
```

## Performance Benchmarks

### Throughput (with cached models)

```bash
# Load test with hey
hey -n 1000 -c 100 -m POST \
  -H "Content-Type: application/json" \
  -d '{"name":"Sasa","lang":"hr"}' \
  http://localhost:8002/suggest

# Results:
# Requests/sec: 904.7
# Average: 82.5 ms
# p50: 42.6 ms
# p90: 120.8 ms
# p99: 902.1 ms
```

## Advanced Configuration

### Using Gunicorn for Multiple Workers

**⚠️ Warning**: Multiple workers significantly increase memory usage due to Python's model loading behavior.

```dockerfile
# Install gunicorn
RUN pip install gunicorn

# Use gunicorn with multiple workers
CMD ["gunicorn", "main:app", \
     "--workers", "2", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000"]
```

**Memory impact:**

```
1 worker:  ~750 MB baseline, ~1.9 GB peak
2 workers: ~1.3 GB baseline, ~3.8 GB peak ❗
```

**When to use multiple workers:**

- High concurrent load (100+ simultaneous users)
- Server has 4+ CPU cores
- Memory limit ≥ 4 GB
- Traffic consistently >100 req/s

**Recommendation**: For most use cases (registration forms, low-medium traffic), **single worker with uvicorn is optimal**.

### Configuration Parameters

```python
# fast_redi.py
class SmartCachingRestorer:
    UNLOAD_TIMEOUT = 30          # 30 seconds - time before unloading unused language
    MAX_CONCURRENT_LOADS = 2      # Max languages loading simultaneously
```

```python
# main.py
RATE_LIMIT_REQUESTS = 10   # Croatian: requests/minute per IP
RATE_LIMIT_NON_HR = 20     # Other: requests/minute per IP
RATE_LIMIT_WINDOW = 60     # Seconds
```

## ⚡ Performance

| Metric | Value |
|--------|-------|
| Cold start | ~2-3 seconds (loading models) |
| Request latency | <10ms (models in memory) |
| Memory usage | ~750-1900 MB (all 3 languages) |
| Throughput | 900+ requests/second |

## 🔄 Differences from Original REDI

| Original REDI | This FastAPI Version |
|---------------|---------------------|
| Python 2.7 | Python 3.12+ |
| Command-line tool | REST API microservice |
| Pipe-based stdin/stdout | JSON HTTP requests/responses |
| No preloading | Models preloaded in memory |
| Single request processing | Async, high-throughput |
| Manual tokenizer invocation | Integrated tokenization |

## Troubleshooting

### Service Unhealthy

```bash
# Check logs
docker compose logs --tail=100

# Verify Croatian model loaded
curl http://localhost:8002/health

# Force restart
docker compose restart
```

### High Memory Usage

```bash
# Check memory
docker stats redi-api

# View loaded languages
curl http://localhost:8002/stats

# Manual restart
docker compose restart
```

## Project Structure

```
redi-api/
├── fast_redi.py          # Smart caching language model loader
├── main.py               # FastAPI application with rate limiting
├── models/               # Language model files (.tm)
│   ├── wikitweetweb.hr.tm
│   ├── wikitweetweb.sl.tm
│   └── wikitweetweb.sr.tm
├── requirements.txt      # Python dependencies
├── Dockerfile            # Container definition
├── docker-compose.yml    # Docker Compose configuration
└── README.md            # This file
```

## Requirements

- Python 3.14+
- Docker \& Docker Compose (for containerized deployment)
- 2.5 GB RAM minimum (4 GB recommended for production)
- 1 CPU core minimum (2+ recommended)

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 🐛 Issues

If you encounter any problems or have questions:

1. Check the [existing issues](https://github.com/dlackovic2/redi-fastapi/issues)
2. For new issues, please provide:
   - Python version
   - Operating system
   - Error messages/logs
   - Steps to reproduce

## 📧 Support

For questions about this FastAPI implementation, please [open an issue](https://github.com/dlackovic2/redi-fastapi/issues).

For questions about the original REDI algorithm, refer to the [original repository](https://github.com/clarinsi/redi).

## 🗺️ Roadmap

- [ ] Confidence scores for suggestions
- [ ] Additional language support
- [ ] WebSocket support for real-time suggestions
- [ ] Add caching layer (Redis)

---

## License

This project uses the REDI (REstoration of DIacritics) models and reldi-tokeniser for text processing.

## 🙏 Credits

Based on the original [REDI](https://github.com/clarinsi/redi) project by Nikola Ljubešić, Tomaž Erjavec, and Darja Fišer.

### Original Reference

```
@InProceedings{ljubesic16-corpus,
author = {Nikola Ljubešić and Tomaž Erjavec and Darja Fišer},
title = {Corpus-Based Diacritic Restoration for South Slavic Languages},
booktitle = {Proceedings of the Tenth International Conference on Language Resources and Evaluation (LREC 2016)},
year = {2016},
month = {may},
date = {23-28},
location = {Portorož, Slovenia},
publisher = {European Language Resources Association (ELRA)},
isbn = {978-2-9517408-9-1}
}

```

**Made with ❤️ for South Slavic languages**
