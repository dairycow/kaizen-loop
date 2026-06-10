build:
    pip install -e .

test:
    python -m pytest

lint:
    python -m ruff check src/

fmt:
    python -m ruff format src/

clean:
    rm -rf build/ dist/ *.egg-info src/*.egg-info

run *ARGS:
    python -m kaizen {{ARGS}}
