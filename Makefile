default: lint test

clean:
	rm -f *.pyc
	rm -rf .tox
	rm -rf *.egg-info
	rm -rf __pycache__
	rm -f pip-selfcheck.json

lint:
	flake8
	pylint3 volvooncall
	pydocstyle volvooncall

test:
	pytest

toxlint:
	tox -e lint

toxtest:
	tox

pypitestreg:
	python setup.py register -r pypitest

pypitest:
	python setup.py sdist upload -r pypitest

pypireg:
	python setup.py register -r pypi

pypi:
	python setup.py sdist
	twine upload dist/*.tar.gz

release:
	git diff-index --quiet HEAD -- && make toxlint && make toxtest && bumpversion patch && make pypi

IMAGE=voc

docker-build:
	docker build -t $(IMAGE) .

docker-run-mqtt:
	docker run \
	        --name voc \
		--restart always \
		--detach \
		--net bridge \
		-v $(HOME)/.config/voc.conf:/app/.config/voc.conf:ro \
		-v $(HOME)/.config/mosquitto_pub:/app/.config/mosquitto_pub:ro \
		$(IMAGE) /app/voc mqtt -vv
