#!/usr/bin/env bash
# dbt execution helper script for data-jobs-pipeline Phase 3

set -e

DBT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DBT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Check if dbt is installed
if ! command -v dbt &> /dev/null; then
    print_error "dbt is not installed. Install with: pip install dbt-postgres"
    exit 1
fi

# Main menu
case "${1:-help}" in
    debug)
        print_header "Testing PostgreSQL Connection"
        dbt debug
        ;;
    
    parse)
        print_header "Validating dbt Model Syntax"
        dbt parse
        print_success "All models parsed successfully"
        ;;
    
    build)
        print_header "Building dbt Models (staging → core → marts)"
        dbt build
        print_success "All models built successfully"
        ;;
    
    run)
        print_header "Executing dbt Models"
        dbt run
        print_success "All models executed successfully"
        ;;
    
    test)
        print_header "Running dbt Tests"
        dbt test
        print_success "All tests passed"
        ;;
    
    docs)
        print_header "Generating dbt Documentation"
        dbt docs generate
        print_success "Documentation generated. Serve with: dbt docs serve"
        ;;
    
    serve)
        print_header "Serving dbt Documentation (localhost:8000)"
        dbt docs serve
        ;;
    
    clean)
        print_header "Cleaning dbt Artifacts"
        dbt clean
        print_success "Cleaned target/ and dbt_packages/"
        ;;
    
    validate)
        print_header "Full Validation Workflow"
        print_warning "Step 1/5: Testing connection..."
        dbt debug || exit 1
        
        print_warning "Step 2/5: Parsing models..."
        dbt parse || exit 1
        
        print_warning "Step 3/5: Building pipeline..."
        dbt build || exit 1
        
        print_warning "Step 4/5: Running tests..."
        dbt test || exit 1
        
        print_warning "Step 5/5: Generating documentation..."
        dbt docs generate || exit 1
        
        print_success "Full validation completed successfully!"
        ;;
    
    help|*)
        cat << 'EOF'
Usage: ./dbt_run.sh <command>

Commands:
  debug       - Test PostgreSQL connectivity
  parse       - Validate dbt model syntax
  build       - Execute full dbt pipeline (staging → core → marts)
  run         - Run models without tests
  test        - Execute all dbt tests
  docs        - Generate documentation
  serve       - Start documentation server (localhost:8000)
  clean       - Clean target/ and dbt_packages/
  validate    - Run full validation workflow (debug → parse → build → test → docs)
  help        - Show this message

Examples:
  ./dbt_run.sh debug       # Check PostgreSQL
  ./dbt_run.sh validate    # Full workflow
  ./dbt_run.sh build       # Build all models
EOF
        ;;
esac
