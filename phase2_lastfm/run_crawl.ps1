# Run Last.fm crawler (default: 1M edges; no legal clearance required for <= 1M).
# Requires: LASTFM_API_KEY in env OR config/api_key.txt with your key.
# Get key: https://www.last.fm/api/account/create

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$target = 1000000
if ($args.Count -ge 1) { $target = [int]$args[0] }

python -m src.collect.crawl_network `
  --config config/config.yaml `
  --seeds data/seeds/seed_users.txt `
  --target-raw-interactions $target
