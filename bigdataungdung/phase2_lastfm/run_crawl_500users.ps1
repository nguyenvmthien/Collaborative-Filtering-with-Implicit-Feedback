# Crawl until ~500 users (target 3.5M raw edges). Resume from existing state.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$target = 3500000
python -m src.collect.crawl_network `
  --config config/config.yaml `
  --seeds data/seeds/seed_users.txt `
  --target-raw-interactions $target
