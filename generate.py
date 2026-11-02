"""Entry point: read the spec and write generated manifests to disk.

Usage:
    python generate.py

Reads spec.json, then for each service writes:
    manifests/kubernetes/<service>.yaml   (ServiceAccount, Deployment, Service)
    manifests/terraform/<service>.tf       (DynamoDB tables, IAM role + policy)
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from generator import generate_kubernetes, generate_terraform

ROOT = Path(__file__).parent
SPEC_PATH = ROOT / "spec.json"
K8S_DIR = ROOT / "manifests" / "kubernetes"
TF_DIR = ROOT / "manifests" / "terraform"


def main() -> None:
    spec = json.loads(SPEC_PATH.read_text())
    platform = spec["platform"]

    K8S_DIR.mkdir(parents=True, exist_ok=True)
    TF_DIR.mkdir(parents=True, exist_ok=True)

    for service in spec["services"]:
        name = service["name"]

        k8s_objects = generate_kubernetes(service, platform)
        (K8S_DIR / f"{name}.yaml").write_text(
            yaml.safe_dump_all(k8s_objects, sort_keys=False)
        )

        terraform = generate_terraform(service, platform)
        (TF_DIR / f"{name}.tf").write_text(terraform)

        print(f"generated manifests for {name}")


if __name__ == "__main__":
    main()
