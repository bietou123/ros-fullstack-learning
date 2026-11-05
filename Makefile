.PHONY: install build dev typecheck test verify verify-full verify-experiments scan package-exe package-deb package-apk clean

install:
	pnpm install

build:
	pnpm build

dev:
	pnpm dev

typecheck:
	pnpm typecheck

test:
	pnpm test

verify:
	pnpm verify

verify-full:
	node scripts/verify.mjs --full --strict

verify-experiments:
	node scripts/verify-experiments.mjs

scan:
	pnpm scan

package-exe:
	pnpm package:exe

package-deb:
	pnpm package:deb

package-apk:
	pnpm package:apk

clean:
	rm -rf dist release apps/web/dist apps/desktop/web apps/web/public/content
