#!/bin/bash

# Check if there is at least one argument
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <serve|build>"
    exit 1
fi

# Copy docs/index.md to README.md
cp docs/index.md README.md

# Depending on the argument, serve or build the site
case $1 in
    serve)
        mkdocs serve
        ;;
    build)
        mkdocs build
        ;;
    *)
        echo "Invalid argument: $1. Use 'serve' or 'build'."
        exit 2
        ;;
esac
