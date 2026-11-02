#!/usr/bin/env bash
# HW8 Part 2: create the pipeline topics with the Kafka CLI inside the s1066_kafka container.
set -euo pipefail
K="docker exec s1066_kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092"
$K --create --if-not-exists --topic s1066_inbox       --partitions 1 --replication-factor 1
$K --create --if-not-exists --topic s1066_tasks       --partitions 2 --replication-factor 1
$K --create --if-not-exists --topic s1066_drafts      --partitions 1 --replication-factor 1
$K --create --if-not-exists --topic s1066_final       --partitions 1 --replication-factor 1
$K --create --if-not-exists --topic s1066_dead_letter --partitions 1 --replication-factor 1
echo "--- s1066 topics ---"
$K --describe 2>/dev/null | grep -E "^Topic: s1066_(inbox|tasks|drafts|final|dead_letter)"
