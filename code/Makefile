.PHONY: verify-hw06 test experiments experiments-fast memory-fixture compact

verify-hw06:
	python scripts/verify_hw06.py

test:
	pytest -q tests

experiments:
	python scripts/run_memory_experiments.py

experiments-fast:
	python scripts/run_memory_experiments.py --fast

memory-fixture:
	python scripts/make_memory_fixture.py

compact:
	python scripts/memory_cli.py /compact

migrate-users-hw07:
	python scripts/migrate_users_hw07.py
	
expired-token:
	@python scripts/make_expired_token.py reader_1066
