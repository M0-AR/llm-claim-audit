PY ?= python3

.PHONY: snapshot live test gif docker-snapshot docker-live clean

snapshot:
	$(PY) scripts/run_all.py --mode snapshot

live:
	$(PY) scripts/run_all.py --mode live

test:
	$(PY) -m unittest discover -s tests -v

gif:
	$(PY) scripts/make_gif.py

docker-snapshot:
	docker compose run --rm --build snapshot

docker-live:
	docker compose run --rm --build live

clean:
	rm -rf results/live data/live-live
