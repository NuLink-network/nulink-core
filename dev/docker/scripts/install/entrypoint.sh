#!/bin/bash

# runs inside docker container with access to local volume.
# needed for local development, creates nulink.egg-info on local disk
# if it doesn't exist.

if [ ! -e /code/nulink.egg-info ]; then
    echo "First time install..."
    python setup.py develop
fi
