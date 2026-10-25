"""Insert a few historical cleanups so the dashboard is not empty.

Usage: python scripts/seed_demo_data.py [--table costwarden-cleanups] [--region us-east-1]
"""
import argparse

import boto3

from costwarden.store.demo import seed_history
from costwarden.store.dynamo import DynamoStore


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", default="costwarden-cleanups")
    ap.add_argument("--region", default=None)
    args = ap.parse_args()
    n = seed_history(DynamoStore(args.table, boto3.Session(region_name=args.region)))
    print(f"Seeded {n} records into {args.table}")


if __name__ == "__main__":
    main()
