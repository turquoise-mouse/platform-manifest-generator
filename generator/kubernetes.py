"""Kubernetes manifest generation.

Turns a service definition from the spec into the Kubernetes objects it needs:
a ServiceAccount (linked to an AWS IAM role via IRSA), a Deployment, and -
for services that expose a port - a Service.

Everything is generated into a single shared namespace. There is no naming
convention applied: object names are taken straight from the spec.
"""

from __future__ import annotations


def _service_account(service: dict, platform: dict) -> dict:
    """ServiceAccount annotated so the pod assumes the service's IAM role (IRSA).

    The `eks.amazonaws.com/role-arn` annotation is what links this Kubernetes
    identity to the AWS IAM role generated in terraform.py.
    """
    role_arn = (
        f"arn:aws:iam::{platform['awsAccountId']}:role/{service['name']}"
    )
    return {
        "apiVersion": "v1",
        "kind": "ServiceAccount",
        "metadata": {
            "name": service["name"],
            "namespace": "default",
            "annotations": {
                "eks.amazonaws.com/role-arn": role_arn,
            },
        },
    }


def _deployment(service: dict, platform: dict) -> dict:
    """Deployment that runs the service's container image."""
    env = [
        {"name": key, "value": value}
        for key, value in service.get("env", {}).items()
    ]

    container = {
        "name": service["name"],
        "image": service["image"],
        "env": env,
    }
    if service.get("port"):
        container["ports"] = [{"containerPort": service["port"]}]

    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": service["name"],
            "namespace": "default",
        },
        "spec": {
            "replicas": service.get("replicas", 1),
            "selector": {"matchLabels": {"app": service["name"]}},
            "template": {
                "metadata": {"labels": {"app": service["name"]}},
                "spec": {
                    "serviceAccountName": service["name"],
                    "containers": [container],
                },
            },
        },
    }


def _service(service: dict) -> dict:
    """ClusterIP Service exposing the deployment's port inside the cluster."""
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": service["name"],
            "namespace": "default",
        },
        "spec": {
            "selector": {"app": service["name"]},
            "ports": [{"port": service["port"], "targetPort": service["port"]}],
        },
    }


def generate_kubernetes(service: dict, platform: dict) -> list[dict]:
    """Return every Kubernetes object for a single service."""
    objects = [
        _service_account(service, platform),
        _deployment(service, platform),
    ]
    if service.get("port"):
        objects.append(_service(service))
    return objects
