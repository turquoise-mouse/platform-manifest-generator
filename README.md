# Platform manifest generator

This repo contains a small manifest **generator**. It reads a
[`spec.json`](spec.json) that describes a platform and the services running on
it, and produces the Kubernetes and AWS (Terraform) manifests needed to deploy
those services.

The generated output is committed under [`manifests/`](manifests/).

## How it fits together

```
spec.json ──▶ generate.py ──▶ manifests/kubernetes/<service>.yaml
                           └─▶ manifests/terraform/<service>.tf
```

## Running it

```bash
pip install -r requirements.txt
python generate.py
```

This regenerates everything under `manifests/`.
