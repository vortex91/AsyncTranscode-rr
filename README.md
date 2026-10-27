# AsyncTranscode-rr 🚀

[![Version](https://img.shields.io/badge/version-1.0.0--beta-blue.svg)](https://github.com/vortex91/AsyncTranscode-rr)
[![Docker](https://img.shields.io/badge/docker-ready-brightgreen.svg)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

A high-performance, hybrid media management and transcoding system built specifically for **Radarr** and **Sonarr** homelabs. 

Unlike traditional monolithic transcoders that choke when a network drops, **AsyncTranscode-rr** is engineered from the ground up for **resilient distributed node execution** over flaky connections—whether you're running worker nodes over Wi-Fi, Tailscale tunnels, or remote links that bounce up and down. It pairs a blazing-fast Rust coordinator with smart, automated Python nodes that feature **live real-time directory monitoring**, instant file processing, deep media cleanup, tag management, and quality profile automation.

---

## 🔥 Why AsyncTranscode-rr?

* **Live Real-Time File Monitoring:** Instantaneous event-driven processing. The moment a new file drops into your monitored path, the system catches it, verifies file stability, and kicks off processing without waiting for a scheduled scan.
* **Network Resilience for Remote Nodes:** Designed for distributed worker nodes. If your Tailscale tunnel drops or Wi-Fi blips, nodes handle connection backoffs gracefully, queue their work, and resume seamlessly without corrupting state or crashing.
* **Blazing Fast Rust Core:** The coordinator is written in Rust, delivering incredible performance, low memory overhead, and lightning-fast database interactions compared to sluggish legacy scripts.
* **Intelligent Media & Subtitle Cleanup:** Automatically strips out unwanted non-English audio tracks, removes unneeded subtitle clutter, and purges annoying spam, watermarks, or promotional tags from `.srt` subtitle files.
* **Advanced Filtering & Tagging:** Surgical control using skip terms, modification date ranges, codec matching, and automated **strip-and-retag** logic to ensure files are never redundantly processed.
* **Automated Profile & State Sync:** Dynamically updates Radarr/Sonarr quality profiles and automatically unmonitors completed series episodes once they are successfully optimized.
* **Effortless Docker Deployment:** Drop-in Docker and Docker Compose configuration gets your nodes up and running in seconds.

---

## 🏗️ System Architecture

- **Rust Coordinator (`media_manager`):** Manages SQLite database tracking, communicates with Radarr/Sonarr APIs, and orchestrates tasks across remote nodes.
- **Python Node Workers (`node_sa.py`):** Standalone, fault-tolerant worker agents that monitor input folders live, interface with FFmpeg for hardware/software accelerated encoding, and manage automated file handoffs.
- **Arr Sync Service (`arr_sync_service.py`):** Targeted or global sync helper to align quality profiles, update tags, and clean up library states.

---

## 🐳 Quick Start (Docker Compose)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/vortex91/AsyncTranscode-rr.git
   cd AsyncTranscode-rr
   ```

2. **Set up your configuration files:**
   ```bash
   cp config_example.json config.json
   cp config_node_sa_example.json config_node_sa.json
   ```
   *Open both files in a text editor and plug in your Radarr/Sonarr API keys, URLs, and storage paths.*

3. **Launch the stack:**
   ```bash
   docker compose up -d
   ```

---

## ⚙️ Configuration & Feature Deep Dive

### 1. Global & Path-Based Filters (`config.json`)
* **Skip Terms:** Instantly bypass junk releases, telesyncs, sports broadcasts, or specific unwanted release groups (`"skip_terms": ["TELESYNC", "DKS", "WWE"]`).
* **Timestamp Filtering:** Target files within specific windows using `modified_after_timestamp` and `modified_before_timestamp` parameters.
* **Codec & Resolution Rules:** Define exact minimum/maximum audio channels, widths, heights, and target codecs to isolate files that actually need re-encoding to HEVC.

### 2. Node Execution & Live Monitoring (`config_node_sa_example.json`)
* **Live Directory Tracking (`path_monitor`):** Continuously watches incoming directories for new files, incorporating file-stability checks to ensure downloads are fully written before encoding starts.
* **Strip and Retag Logic (`check_already_tagged`):** Automatically sweeps legacy tags, injects success tags (e.g., `AsyncTranscode-rr`, `TdarrProcessed`, `HEVC_Processed`), and prevents infinite processing loops.
* **Audio & Subtitle Policies:** Force-keep specific audio tracks (like English fallback) and clean foreign or redundant subtitle streams.

### 3. Arr Integration (`arr_sync_service.py`)
* **Quality Profile Updating:** Automatically shifts items into optimized quality profiles (e.g., "no upgrade") once processed.
* **Episode Unmonitoring:** Keeps your Sonarr lists clean by automatically unmonitoring completed series episodes that have already been transcoded and tagged.

---

## ☕ Support & Donations

If AsyncTranscode-rr has streamlined your homelab storage and kept your distributed nodes humming along smoothly, consider supporting its development:

* **Buy Me a Coffee:** [https://buymeacoffee.com/vortex91]
