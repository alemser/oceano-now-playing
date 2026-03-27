# Go Migration Plan for oceano-now-playing

## Recommendation

Yes, migrate to Go, but avoid a big-bang rewrite.

Reasoning:
- Strong language alignment with oceano-player (already in Go)
- Simpler Raspberry Pi deployment (single static binary, no venv)
- Better control of concurrency, timeouts, and long-running loops
- Lower operational complexity and easier production support

Caution:
- Rewriting everything at once risks regressions in edge-case behavior (metadata timing, artwork fallback policy, standby logic)

## Migration Strategy

Use an incremental strangler approach:

1. Freeze behavior contract
- Document the exact state schema and transitions
- Document timing rules and edge-case handling
- Define expected behavior for unknown metadata and fallback artwork

2. Capture real metadata sessions
- Record FIFO streams from real usage
- Include normal playback, sparse metadata, mid-session attach, stop/start bursts
- Use these streams as replay fixtures

3. Build Go metadata parser first
- Implement shairport metadata item parsing in Go
- Normalize output to match current Python state structure
- Validate via golden tests against captured sessions

4. Port state machine second
- Port transition logic and interpolation exactly
- Preserve standby, wake, mode alternation, and artwork refresh policy
- Add parity tests comparing Python and Go outcomes on replay inputs

5. Port renderer third
- Implement framebuffer rendering pipeline in Go
- Keep visual parity first; optimize later
- Preserve text/artwork/hybrid/rotate behavior

6. Run shadow mode on Raspberry Pi
- Run Go app in dry-run or observer mode while Python remains active
- Compare emitted state and decisions in logs
- Fix drift before cutover

7. Controlled cutover with rollback
- Add new systemd service for Go binary
- Keep Python service installed for immediate rollback
- Promote Go service only after stability criteria are met

## Suggested Go Architecture

- cmd/oceano-now-playing
  - Application entrypoint and dependency wiring
- internal/config
  - Environment parsing and validation
- internal/metadata
  - FIFO reader, parser, source classification
- internal/state
  - State machine, seek interpolation, mode cycling
- internal/artwork
  - Provider chain, cache, timeout budget logic
- internal/render/fb
  - Framebuffer writer and drawing pipeline
- internal/app
  - Orchestration loop, lifecycle, reconnect behavior

## Success Criteria

- Functional parity with current Python behavior for known replay scenarios
- Stable operation on Raspberry Pi for prolonged playback sessions
- Fast rollback path verified
- Deployment and update workflow simplified

## Practical Next Step

Phase 1 execution starter:
- Scaffold Go module and folders
- Implement FIFO parser only
- Add replay-based parity tests
- Keep Python service as production runtime until parity is demonstrated
