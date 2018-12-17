default: check

black:
	white . voc

lint: requirements.txt setup.py
	tox -e lint

test: requirements.txt setup.py
	tox

check: lint test


clean:
	rm -f *.pyc
	rm -rf .tox
	rm -rf *.egg-info
	rm -rf __pycache__
	rm -f pip-selfcheck.json

pypitestreg:
	python setup.py register -r pypitest

pypitest:
	python setup.py sdist upload -r pypitest

pypireg:
	python setup.py register -r pypi

pypi:
	rm -f dist/*.tar.gz
	python3 setup.py sdist
	twine upload dist/*.tar.gz

release:
	git diff-index --quiet HEAD -- && make check && bumpversion patch && git push --tags && git push && make pypi

IMAGE=molobrakos/volvooncall

docker-build:
	docker build -t $(IMAGE) .

docker-run-mqtt:
	docker run \
                --name=volvooncall \
		--restart=always \
		--detach \
		--net=bridge \
		-v $(HOME)/.config/voc.conf:/app/.config/voc.conf:ro \
		-v $(HOME)/.config/mosquitto_pub:/app/.config/mosquitto_pub:ro \
		$(IMAGE) -vv

docker-run-mqtt-term:
	docker run \
                -ti --rm \
                --name=volvooncall \
		--net=bridge \
		-v $(HOME)/.config/voc.conf:/app/.config/voc.conf:ro \
		-v $(HOME)/.config/mosquitto_pub:/app/.config/mosquitto_pub:ro \
		$(IMAGE) -vv
