import mimetypes
import os
import sys
import uuid
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


def build_multipart(field_name, filename, content, boundary):
    lines = []
    lines.append(f"--{boundary}")
    lines.append(
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"'
    )
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    lines.append(f"Content-Type: {content_type}")
    lines.append("")
    body = "\r\n".join(lines).encode("utf-8") + b"\r\n" + content + b"\r\n"
    body += f"--{boundary}--\r\n".encode("utf-8")
    return body


def upload_file(host, username, token, local_path, remote_path):
    boundary = uuid.uuid4().hex
    with open(local_path, "rb") as handle:
        content = handle.read()

    body = build_multipart("content", os.path.basename(local_path), content, boundary)
    url = (
        f"https://{host}/api/v0/user/{username}/files/path"
        f"{quote(remote_path, safe='/')}"
    )
    request = Request(url, data=body, method="POST")
    request.add_header("Authorization", f"Token {token}")
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    request.add_header("Content-Length", str(len(body)))
    with urlopen(request) as response:
        if response.status not in (200, 201):
            raise RuntimeError(f"Upload failed for {remote_path}: {response.status}")


def reload_webapp(host, username, token, domain):
    url = f"https://{host}/api/v0/user/{username}/webapps/{domain}/reload/"
    request = Request(url, data=b"", method="POST")
    request.add_header("Authorization", f"Token {token}")
    with urlopen(request) as response:
        if response.status not in (200, 201, 204):
            raise RuntimeError(f"Reload failed: {response.status}")


def should_skip(path):
    parts = path.parts
    if any(part.startswith(".") for part in parts):
        return True
    if "node_modules" in parts or "__pycache__" in parts:
        return True
    if "scripts" in parts:
        return True
    return False


def main():
    username = os.environ.get("PA_USERNAME")
    token = os.environ.get("PA_TOKEN")
    host = os.environ.get("PA_HOST", "hackit.pythonanywhere.com")
    target_root = os.environ.get("PA_TARGET", "/home/hackit/code")
    domain = os.environ.get("PA_DOMAIN")

    if not username or not token:
        raise SystemExit("PA_USERNAME and PA_TOKEN are required.")

    repo_root = Path(__file__).resolve().parents[1]
    uploaded = 0
    for path in repo_root.rglob("*"):
        if path.is_dir():
            continue
        rel = path.relative_to(repo_root)
        if should_skip(rel):
            continue
        remote_path = f"{target_root}/{rel.as_posix()}"
        upload_file(host, username, token, str(path), remote_path)
        uploaded += 1

    if domain:
        reload_webapp(host, username, token, domain)

    print(f"Uploaded {uploaded} files to {target_root}")
    if domain:
        print(f"Reloaded webapp {domain}")
    else:
        print("PA_DOMAIN not set; skipping reload.")


if __name__ == "__main__":
    main()
