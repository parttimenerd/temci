#! /bin/sh

cd "$(dirname "$0")"
pytest --doctest-modules --doctest-glob='*.rst'

