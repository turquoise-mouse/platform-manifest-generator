"""Terraform (AWS) generation.

Turns a service definition from the spec into the AWS resources it needs:
a DynamoDB table per `dynamodb` resource, an IAM role the service's pod can
assume via IRSA, and an inline IAM policy granting that role access to its
tables.

Output is Terraform HCL. IAM policy documents are emitted with `jsonencode(...)`
so they read as structured HCL rather than embedded JSON strings.

Table names are taken straight from the spec - there is no naming convention
or environment prefixing applied.
"""

from __future__ import annotations

import re

# DynamoDB actions granted for each access level.
_READ_ACTIONS = [
    "dynamodb:GetItem",
    "dynamodb:BatchGetItem",
    "dynamodb:Query",
    "dynamodb:Scan",
    "dynamodb:DescribeTable",
]
_WRITE_ACTIONS = [
    "dynamodb:PutItem",
    "dynamodb:UpdateItem",
    "dynamodb:DeleteItem",
    "dynamodb:BatchWriteItem",
]

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def _hcl(value, indent: int = 0) -> str:
    """Render a Python value as an HCL expression (used inside jsonencode)."""
    pad = "  " * indent
    child_pad = "  " * (indent + 1)

    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list):
        if not value:
            return "[]"
        items = ",\n".join(child_pad + _hcl(v, indent + 1) for v in value)
        return f"[\n{items}\n{pad}]"
    if isinstance(value, dict):
        if not value:
            return "{}"
        lines = []
        for key, val in value.items():
            label = key if _IDENTIFIER.match(key) else f'"{key}"'
            lines.append(f"{child_pad}{label} = {_hcl(val, indent + 1)}")
        return "{\n" + "\n".join(lines) + f"\n{pad}}}"
    raise TypeError(f"unsupported HCL value: {value!r}")


def _dynamodb_table_block(resource: dict) -> str:
    """An aws_dynamodb_table resource block for a single dynamodb resource."""
    return (
        f'resource "aws_dynamodb_table" "{resource["name"]}" {{\n'
        f'  name         = "{resource["name"]}"\n'
        f'  billing_mode = "PAY_PER_REQUEST"\n'
        f'  hash_key     = "{resource["hashKey"]}"\n'
        f"\n"
        f"  attribute {{\n"
        f'    name = "{resource["hashKey"]}"\n'
        f'    type = "S"\n'
        f"  }}\n"
        f"}}\n"
    )


def _assume_role_policy(service: dict, platform: dict) -> dict:
    """Trust policy allowing the service's Kubernetes ServiceAccount to assume
    this role through the cluster's OIDC provider (IRSA)."""
    provider = platform["oidcProvider"]
    account = platform["awsAccountId"]
    subject = f"system:serviceaccount:default:{service['name']}"

    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Federated": (
                        f"arn:aws:iam::{account}:oidc-provider/{provider}"
                    )
                },
                "Action": "sts:AssumeRoleWithWebIdentity",
                "Condition": {"StringEquals": {f"{provider}:sub": subject}},
            }
        ],
    }


def _table_actions(access: str) -> list[str]:
    if access == "readwrite":
        return _READ_ACTIONS + _WRITE_ACTIONS
    return _READ_ACTIONS


def _inline_policy(service: dict, platform: dict) -> dict:
    """Inline policy granting the role access to each of its DynamoDB tables."""
    region = platform["awsRegion"]
    account = platform["awsAccountId"]

    statements = []
    for resource in service.get("resources", []):
        if resource["type"] != "dynamodb":
            continue
        table_arn = (
            f"arn:aws:dynamodb:{region}:{account}:table/{resource['name']}"
        )
        statements.append(
            {
                "Effect": "Allow",
                "Action": _table_actions(resource["access"]),
                "Resource": [table_arn, f"{table_arn}/index/*"],
            }
        )

    return {"Version": "2012-10-17", "Statement": statements}


def _iam_role_block(service: dict, platform: dict) -> str:
    """The aws_iam_role resource block, including its IRSA trust policy."""
    policy = _hcl(_assume_role_policy(service, platform), indent=1)
    return (
        f'resource "aws_iam_role" "{service["name"]}" {{\n'
        f'  name = "{service["name"]}"\n'
        f"\n"
        f"  assume_role_policy = jsonencode({policy})\n"
        f"}}\n"
    )


def _iam_role_policy_block(service: dict, platform: dict) -> str:
    """The aws_iam_role_policy resource block granting DynamoDB access."""
    policy = _hcl(_inline_policy(service, platform), indent=1)
    return (
        f'resource "aws_iam_role_policy" "{service["name"]}" {{\n'
        f'  name = "{service["name"]}"\n'
        f"  role = aws_iam_role.{service['name']}.id\n"
        f"\n"
        f"  policy = jsonencode({policy})\n"
        f"}}\n"
    )


def generate_terraform(service: dict, platform: dict) -> str:
    """Return the Terraform HCL document for a single service."""
    tables = [
        resource
        for resource in service.get("resources", [])
        if resource["type"] == "dynamodb"
    ]

    blocks = [_iam_role_block(service, platform)]
    for table in tables:
        blocks.append(_dynamodb_table_block(table))
    if tables:
        blocks.append(_iam_role_policy_block(service, platform))

    return "\n".join(blocks)
