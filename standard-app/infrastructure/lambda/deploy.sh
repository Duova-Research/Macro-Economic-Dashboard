#!/bin/bash
# infrastructure/lambda/deploy.sh
# ────────────────────────────────
# Packages the backend code and deploys it as an AWS Lambda function.
#
# Prerequisites:
#   - AWS CLI installed and configured (aws configure)
#   - Python 3.11+ installed locally
#   - Lambda execution role already created in IAM
#
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh
#
# Environment variables to set before running:
#   AWS_REGION      e.g. "us-east-1"
#   AWS_ACCOUNT_ID  your 12-digit AWS account ID
#   LAMBDA_ROLE_ARN arn:aws:iam::ACCOUNT_ID:role/macro-dashboard-lambda-role

set -e   # Exit immediately on any error

# ── Configuration ─────────────────────────────────────────────────────────────
FUNCTION_NAME="macro-dashboard-fetcher"
RUNTIME="python3.11"
HANDLER="handler.handler"                   # handler.py → handler() function
REGION="${AWS_REGION:-us-east-1}"
ROLE_ARN="${LAMBDA_ROLE_ARN}"
BUILD_DIR="/tmp/macro-lambda-build"
ZIP_PATH="/tmp/macro-lambda.zip"

echo "=== Macro Dashboard Lambda Deploy ==="
echo "Function : $FUNCTION_NAME"
echo "Region   : $REGION"
echo ""

# ── Step 1: Clean build directory ─────────────────────────────────────────────
echo "[1/5] Cleaning build directory…"
rm -rf "$BUILD_DIR" "$ZIP_PATH"
mkdir -p "$BUILD_DIR"

# ── Step 2: Copy backend source files ─────────────────────────────────────────
echo "[2/5] Copying source files…"
cp handler.py "$BUILD_DIR/"
mkdir -p "$BUILD_DIR/data"
cp ../../backend/data/fetcher.py "$BUILD_DIR/data/"
cp ../../backend/data/processor.py "$BUILD_DIR/data/"
cp ../../backend/data/database.py "$BUILD_DIR/data/"
touch "$BUILD_DIR/data/__init__.py"

# ── Step 3: Install Python dependencies into build dir ────────────────────────
echo "[3/5] Installing dependencies…"
pip install \
  requests \
  pandas \
  sqlalchemy \
  python-dotenv \
  --target "$BUILD_DIR" \
  --quiet

# ── Step 4: Zip the package ───────────────────────────────────────────────────
echo "[4/5] Creating deployment zip…"
cd "$BUILD_DIR"
zip -r "$ZIP_PATH" . -x "*.pyc" -x "__pycache__/*" > /dev/null
cd -
echo "Zip size: $(du -sh $ZIP_PATH | cut -f1)"

# ── Step 5: Deploy to Lambda ──────────────────────────────────────────────────
echo "[5/5] Deploying to AWS Lambda…"

# Check if function exists
EXISTING=$(aws lambda get-function \
  --function-name "$FUNCTION_NAME" \
  --region "$REGION" \
  --query 'Configuration.FunctionName' \
  --output text 2>/dev/null || echo "")

if [ -z "$EXISTING" ]; then
  # Create new Lambda function
  echo "Creating new Lambda function…"
  aws lambda create-function \
    --function-name "$FUNCTION_NAME" \
    --runtime "$RUNTIME" \
    --role "$ROLE_ARN" \
    --handler "$HANDLER" \
    --zip-file "fileb://$ZIP_PATH" \
    --timeout 60 \
    --memory-size 256 \
    --region "$REGION" \
    --environment "Variables={
      FRED_API_KEY=${FRED_API_KEY},
      DATABASE_URL=${DATABASE_URL:-sqlite:////mnt/efs/macro_data.db},
      API_REFRESH_URL=${API_REFRESH_URL:-},
      API_SECRET=${API_SECRET:-}
    }" \
    --description "Daily FRED macro data fetch for the Macro Dashboard"
else
  # Update existing Lambda function code
  echo "Updating existing Lambda function…"
  aws lambda update-function-code \
    --function-name "$FUNCTION_NAME" \
    --zip-file "fileb://$ZIP_PATH" \
    --region "$REGION"
fi

# ── Step 6: Create/update EventBridge schedule ────────────────────────────────
echo "[+] Setting up EventBridge daily trigger (06:00 UTC)…"

RULE_ARN=$(aws events put-rule \
  --name "macro-dashboard-daily-fetch" \
  --schedule-expression "cron(0 6 * * ? *)" \
  --state ENABLED \
  --region "$REGION" \
  --query 'RuleArn' \
  --output text)

LAMBDA_ARN="arn:aws:lambda:${REGION}:${AWS_ACCOUNT_ID}:function:${FUNCTION_NAME}"

# Add Lambda as target of the EventBridge rule
aws events put-targets \
  --rule "macro-dashboard-daily-fetch" \
  --targets "Id=MacroDashboardFetcher,Arn=${LAMBDA_ARN}" \
  --region "$REGION"

# Grant EventBridge permission to invoke the Lambda
aws lambda add-permission \
  --function-name "$FUNCTION_NAME" \
  --statement-id "EventBridgeDailyInvoke" \
  --action "lambda:InvokeFunction" \
  --principal "events.amazonaws.com" \
  --source-arn "$RULE_ARN" \
  --region "$REGION" \
  2>/dev/null || true  # Ignore error if permission already exists

echo ""
echo "=== Deploy complete ==="
echo "Lambda ARN : $LAMBDA_ARN"
echo "Schedule   : Daily at 06:00 UTC"
echo ""
echo "Test invoke:"
echo "  aws lambda invoke --function-name $FUNCTION_NAME --region $REGION /tmp/response.json"
echo "  cat /tmp/response.json"
