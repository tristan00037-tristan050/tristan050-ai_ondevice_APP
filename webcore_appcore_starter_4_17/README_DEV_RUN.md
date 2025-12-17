# Local Dev Run (SOP)

## Standard ports
- BFF: 8081
- Web: 8083

## Start (standard)
Terminal A:
- ./scripts/dev_bff.sh
- Force restart: ./scripts/dev_bff.sh restart

Terminal B:
- ./scripts/dev_web.sh

Terminal C:
- ./scripts/dev_check.sh

## One-command (tmux required)
- ./scripts/dev_all.sh

## Policy gate
- npm run policy:check

## Live QA evidence
1) CS tickets: 200 OK
2) DevTools Network: POST /v1/os/llm-usage
   - Payload: eventType, suggestionLength only
   - No raw text fields
   - Headers: X-Tenant, X-User-Id, X-User-Role

