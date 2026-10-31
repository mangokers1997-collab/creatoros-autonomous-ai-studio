import json
import sys
import urllib.error
import urllib.request

url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/health"
try:
    with urllib.request.urlopen(url, timeout=5) as response:
        body = json.loads(response.read().decode("utf-8"))
        if response.status != 200 or body.get("status") != "ok":
            raise SystemExit("CreatorOS health check returned an unexpected response")
        print(json.dumps(body))
except (urllib.error.URLError, TimeoutError, ValueError) as exc:
    print(f"CreatorOS health check failed: {exc}", file=sys.stderr)
    raise SystemExit(1)
