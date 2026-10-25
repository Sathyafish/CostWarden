#!/usr/bin/env bash
# Builds build/lambda.zip for the CostWarden Lambdas (Linux x86_64, Python 3.12).
# Run from the repo root: scripts/build_lambda.sh
set -euo pipefail

cd "$(dirname "$0")/.."
rm -rf build/package build/lambda.zip
mkdir -p build/package

pip install --quiet --target build/package \
  --platform manylinux2014_x86_64 --implementation cp --python-version 3.12 --only-binary=:all: \
  langgraph langchain-core langchain-ollama langchain-openai python-hcl2 PyGithub pyyaml python-dotenv

cp -R costwarden config data sample_terraform build/package/
find build/package -name "__pycache__" -type d -prune -exec rm -rf {} +
find build/package -name "*.dist-info" -type d -prune -exec rm -rf {} +

(cd build/package && zip -q -r ../lambda.zip .)
echo "Built build/lambda.zip ($(du -h build/lambda.zip | cut -f1))"
