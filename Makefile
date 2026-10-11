.PHONY: dev-api dev-ui up up-llm down demo test test-backend test-frontend e2e bench prebake offline-test check-ocsf lint

dev-api:        ; PYTHONPATH=. ANVAYA_DEMO_MODE=1 ANVAYA_DATA_DIR=./data uvicorn app.main:create_app --factory --reload --app-dir backend --port 8000
dev-ui:         ; cd frontend && npm run dev
up:             ; docker compose up -d
up-llm:         ; docker compose --profile llm up -d
down:           ; docker compose --profile llm down
demo:           ; ./demo.sh
test: test-backend test-frontend
test-backend:   ; cd backend && pytest -q
test-frontend:  ; cd frontend && npm run lint && npx vitest run
e2e:            ; ./demo.sh --speed 40 && cd frontend && npx playwright test e2e/golden-path.spec.ts
bench:          ; python bench/load_test.py --api http://localhost:8000 --out docs/BENCHMARKS.md
prebake:        ; docker compose exec api python -m app.aiparser.prebake && docker compose cp api:/srv/app/aiparser/cache/acme-edge.json backend/app/aiparser/cache/acme-edge.json
offline-test:   ; docker run --rm --network none -e ANVAYA_DEMO_MODE=1 -e ANVAYA_DATA_DIR=/tmp/anvaya anvaya-api python -m app.selfcheck
check-ocsf:     ; cd backend && python -m app.ocsf.validate --check-vendored
lint:           ; cd backend && ruff check . && cd ../frontend && npm run lint
