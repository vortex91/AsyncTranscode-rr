# Stage 1: Build Rust Coordinator
FROM rust:1.75-slim AS builder
WORKDIR /app
COPY Cargo.toml Cargo.lock ./
COPY src/ ./src/
RUN cargo build --release

# Stage 2: Runtime Image
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python scripts
COPY node_sa.py arr_sync_service.py ./

# Copy compiled Rust coordinator from Stage 1
COPY --from=builder /app/target/release/media_manager /app/media_manager

# Command to run your node service
CMD ["python3", "node_sa.py"]
