#!/bin/sh
export PYTHONPATH=src
python3 -m src.benchmark.freeform_bench --questions 20 > /tmp/bench_output.txt 2>&1
echo "EXIT_CODE=$?" >> /tmp/bench_output.txt
