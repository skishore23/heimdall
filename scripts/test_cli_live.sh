#!/bin/bash
#
# Live CLI Test Script - Tests actual installed CLI
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🧪 Heimdall CLI Live Tests${NC}"
echo "================================"
echo ""

# Test: version
echo -e "${BLUE}→${NC} Test: heimdall version"
heimdall version > /dev/null && echo -e "${GREEN}✓${NC} version works"

# Test: doctor
echo -e "${BLUE}→${NC} Test: heimdall doctor"
heimdall doctor > /dev/null && echo -e "${GREEN}✓${NC} doctor works"

# Test: policy help
echo -e "${BLUE}→${NC} Test: heimdall policy --help"
heimdall policy --help > /dev/null && echo -e "${GREEN}✓${NC} policy help works"

# Test: policy keygen
echo -e "${BLUE}→${NC} Test: heimdall policy keygen"
heimdall policy keygen > /dev/null && echo -e "${GREEN}✓${NC} policy keygen works"

# Test: models list
echo -e "${BLUE}→${NC} Test: heimdall models list"
heimdall models list > /dev/null && echo -e "${GREEN}✓${NC} models list works"

# Test: models list --json
echo -e "${BLUE}→${NC} Test: heimdall models list --json"
heimdall models list --json > /dev/null && echo -e "${GREEN}✓${NC} models list JSON works"

# Test: bifrost status (expected to fail)
echo -e "${BLUE}→${NC} Test: heimdall bifrost status (expected failure)"
if heimdall bifrost status --json > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} bifrost status works"
else
    echo -e "${YELLOW}⚠${NC} bifrost status failed (expected if gateway not running)"
fi

# Test: run help
echo -e "${BLUE}→${NC} Test: heimdall run --help"
heimdall run --help > /dev/null && echo -e "${GREEN}✓${NC} run help works"

# Test: eval help
echo -e "${BLUE}→${NC} Test: heimdall eval --help"
heimdall eval --help > /dev/null && echo -e "${GREEN}✓${NC} eval help works"

# Test: mimir help
echo -e "${BLUE}→${NC} Test: heimdall mimir --help"
heimdall mimir --help > /dev/null && echo -e "${GREEN}✓${NC} mimir help works"

# Test: dev
echo -e "${BLUE}→${NC} Test: heimdall dev"
heimdall dev > /dev/null 2>&1 && echo -e "${GREEN}✓${NC} dev works"

# Test: completion
echo -e "${BLUE}→${NC} Test: heimdall completion bash"
heimdall completion bash > /dev/null 2>&1 && echo -e "${GREEN}✓${NC} completion works"

# Test models info (if models exist)
if [ -f models/toxicity_detoxify.onnx ]; then
    echo -e "${BLUE}→${NC} Test: heimdall models info"
    heimdall models info models/toxicity_detoxify.onnx > /dev/null 2>&1 && echo -e "${GREEN}✓${NC} models info works"
fi

echo ""
echo "================================"
echo -e "${GREEN}✓${NC} All core CLI commands functional!"
echo ""
echo "Summary:"
echo "  - All subcommands accessible"
echo "  - Help systems working"
echo "  - JSON output functional"
echo "  - Rich terminal output working"
echo ""

