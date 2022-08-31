#!/bin/bash
args="$@"
docker-compose run nulink-dev pytest $args
