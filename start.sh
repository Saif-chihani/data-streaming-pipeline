#!/bin/bash

# Start script for the engagement streaming pipeline
# This script sets up the environment and starts all services

set -e

echo "Starting Engagement Streaming Pipeline..."

# Function to wait for service to be ready
wait_for_service() {
    local service_name=$1
    local host=$2
    local port=$3
    local max_attempts=30
    local attempt=1

    echo "Waiting for $service_name to be ready..."
    
    while [ $attempt -le $max_attempts ]; do
        if nc -z $host $port; then
            echo "$service_name is ready!"
            return 0
        fi
        
        echo "Attempt $attempt/$max_attempts: $service_name not ready yet..."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    echo "ERROR: $service_name failed to start within expected time"
    return 1
}

# Create necessary directories
mkdir -p config
mkdir -p logs

# Copy environment file if it doesn't exist
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env file from template. Please update with your configurations."
fi

# Start infrastructure services
echo "Starting infrastructure services..."
docker-compose up -d postgres redis zookeeper kafka

# Wait for services to be ready
wait_for_service "PostgreSQL" localhost 5432
wait_for_service "Redis" localhost 6379
wait_for_service "Kafka" localhost 9092

# Start Kafka Connect
echo "Starting Kafka Connect..."
docker-compose up -d kafka-connect

# Wait for Kafka Connect
wait_for_service "Kafka Connect" localhost 8083

# Setup Kafka topics
echo "Setting up Kafka topics..."
docker exec kafka kafka-topics --create \
    --bootstrap-server localhost:9092 \
    --replication-factor 1 \
    --partitions 3 \
    --topic engagement-events \
    --if-not-exists

# Start application services
echo "Starting application services..."
docker-compose up -d data-generator stream-processor

echo "All services started successfully!"
echo ""
echo "Services available at:"
echo "  - PostgreSQL: localhost:5432"
echo "  - Redis: localhost:6379"
echo "  - Kafka: localhost:9092"
echo "  - Kafka Connect: localhost:8083"
echo ""
echo "To view logs:"
echo "  docker-compose logs -f [service-name]"
echo ""
echo "To stop all services:"
echo "  docker-compose down"
