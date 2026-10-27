__version__ = "1.0.0-beta"
import os
import sys
import time
import sqlite3
import json

try:
    import requests
except ImportError:
    requests = None

CONFIG_FILE = "config.json"

def load_config():
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(f"Configuration file '{CONFIG_FILE}' not found!")
    
    with open(CONFIG_FILE, "r", encoding="utf-8", errors="ignore") as f:
        processed_lines = []
        for line in f:
            in_string = False
            escaped = False
            comment_idx = -1
            for i, char in enumerate(line):
                if escaped:
                    escaped = False
                    continue
                if char == '\\':
                    escaped = True
                    continue
                if char == '"':
                    in_string = not in_string
                elif not in_string and char == '/' and i + 1 < len(line) and line[i+1] == '/':
                    comment_idx = i
                    break
            if comment_idx != -1:
                line = line[:comment_idx] + "\n"
            processed_lines.append(line)
        return json.loads("".join(processed_lines), strict=False)

config_data = load_config()

DB_FILE_PATH = config_data.get("db_file_path", "media_database.db")

RADARR_URL = os.getenv("RADARR_URL", config_data.get("radarr_url"))
if RADARR_URL:
    RADARR_URL = RADARR_URL.rstrip("/")
RADARR_API_KEY = os.getenv("RADARR_API_KEY", config_data.get("radarr_api_key"))

SONARR_URL = os.getenv("SONARR_URL", config_data.get("sonarr_url"))
if SONARR_URL:
    SONARR_URL = SONARR_URL.rstrip("/")
SONARR_API_KEY = os.getenv("SONARR_API_KEY", config_data.get("sonarr_api_key"))

if not RADARR_URL or not RADARR_API_KEY:
    print("❌ [CONFIG ERROR] Radarr URL or API Key is missing from config.json!", flush=True)
if not SONARR_URL or not SONARR_API_KEY:
    print("❌ [CONFIG ERROR] Sonarr URL or API Key is missing from config.json!", flush=True)

def log(msg):
    print(f"[{time.strftime('%H:%M:%S' )}] [ARR SYNC] {msg}", flush=True)

def get_db_connection():
    conn = sqlite3.connect(DB_FILE_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def build_radarr_filter_sql(filter_config):
    if not filter_config:
        return ""
    status_clause = ""
    other_clauses = []

    target_statuses = filter_config.get("target_statuses", [])
    if target_statuses:
        status_list = ", ".join([f"'{s}'" for s in target_statuses])
        status_clause = f"status IN ({status_list})"

    min_audio = filter_config.get("min_audio_channels")
    if min_audio is not None:
        other_clauses.append(f"audio_channels >= {min_audio}")

    min_h = filter_config.get("min_height")
    max_h = filter_config.get("max_height")
    if min_h is not None or max_h is not None:
        if min_h is not None and max_h is not None:
            other_clauses.append(f"CAST(SUBSTR(resolution, INSTR(resolution, 'x') + 1) AS INTEGER) BETWEEN {min_h} AND {max_h}")
        elif min_h is not None:
            other_clauses.append(f"CAST(SUBSTR(resolution, INSTR(resolution, 'x') + 1) AS INTEGER) >= {min_h}")
        elif max_h is not None:
            other_clauses.append(f"CAST(SUBSTR(resolution, INSTR(resolution, 'x') + 1) AS INTEGER) <= {max_h}")

    min_w = filter_config.get("min_width")
    max_w = filter_config.get("max_width")
    if min_w is not None or max_w is not None:
        if min_w is not None and max_w is not None:
            other_clauses.append(f"CAST(SUBSTR(resolution, 1, INSTR(resolution, 'x') - 1) AS INTEGER) BETWEEN {min_w} AND {max_w}")
        elif min_w is not None:
            other_clauses.append(f"CAST(SUBSTR(resolution, 1, INSTR(resolution, 'x') - 1) AS INTEGER) >= {min_w}")
        elif max_w is not None:
            other_clauses.append(f"CAST(SUBSTR(resolution, 1, INSTR(resolution, 'x') - 1) AS INTEGER) <= {max_w}")

    target_tags = filter_config.get("target_tags", [])
    if target_tags:
        tag_clauses = " OR ".join([f"tag LIKE '%{t}%'" for t in target_tags])
        other_clauses.append(f"({tag_clauses})")

    other_sql = " AND ".join(other_clauses) if other_clauses else ""

    if status_clause and other_sql:
        return f" AND ({status_clause} OR ({other_sql}))"
    elif status_clause:
        return f" AND ({status_clause})"
    elif other_sql:
        return f" AND ({other_sql})"
    return ""

def run_media_profile_and_unmonitor_sync(target_path=None):
    if not requests:
        log("❌ Requests library not installed.")
        return
    
    cfg = load_config()
    profile_rules = cfg.get("media_profile_rules", [])
    unmonitor_rules = cfg.get("sonarr_unmonitor_rules", [])

    conn = get_db_connection()
    cursor = conn.cursor()

    headers_radarr = {"X-Api-Key": RADARR_API_KEY}
    headers_sonarr = {"X-Api-Key": SONARR_API_KEY}

    radarr_rules = [r for r in profile_rules if r.get("type") == "radarr" and r.get("quality_profile", "").strip()]
    log(f"🔍 Found {len(radarr_rules)} Radarr profile rule(s) in config.")

    if radarr_rules:
        pending_radarr_tasks = []
        for idx, rule in enumerate(radarr_rules):
            target_profile_name = rule.get("quality_profile", "").lower()
            prefixes = rule.get("paths", [])
            path_conditions = " OR ".join([f"path LIKE '{p}/%'" for p in prefixes])
            filter_sql = build_radarr_filter_sql(rule.get("filter_config", {}))

            if target_path:
                query = f"""
                    SELECT path FROM media_files 
                    WHERE path = ? AND (radarr_quality_profile != ? OR radarr_quality_profile IS NULL)
                      AND ({path_conditions}) {filter_sql}
                """
                cursor.execute(query, (target_path, target_profile_name))
            else:
                query = f"""
                    SELECT path FROM media_files 
                    WHERE (radarr_quality_profile != ? OR radarr_quality_profile IS NULL)
                      AND ({path_conditions}) {filter_sql}
                """
                cursor.execute(query, (target_profile_name,))
            
            rows = cursor.fetchall()
            if rows:
                pending_radarr_tasks.append((idx, rule, target_profile_name, rows))

        if pending_radarr_tasks:
            try:
                m_res = requests.get(f"{RADARR_URL}/api/v3/movie", headers=headers_radarr, timeout=15)
                p_res = requests.get(f"{RADARR_URL}/api/v3/qualityprofile", headers=headers_radarr, timeout=15)

                if m_res.status_code == 200 and p_res.status_code == 200:
                    radarr_movies = m_res.json()
                    profiles = p_res.json()
                    profile_map = {p["name"].lower(): p["id"] for p in profiles}
                    path_to_radarr_movie = {rm.get("path", "").rstrip("/"): rm for rm in radarr_movies if rm.get("path")}

                    for idx, rule, target_profile_name, rows in pending_radarr_tasks:
                        target_profile_id = profile_map.get(target_profile_name)
                        if not target_profile_id:
                            continue

                        for (path,) in rows:
                            movie_folder = os.path.dirname(path).rstrip("/")
                            radarr_movie = path_to_radarr_movie.get(movie_folder)

                            if radarr_movie:
                                movie_id = radarr_movie["id"]
                                current_profile_id = radarr_movie.get("qualityProfileId")

                                if current_profile_id != target_profile_id:
                                    radarr_movie["qualityProfileId"] = target_profile_id
                                    put_res = requests.put(f"{RADARR_URL}/api/v3/movie/{movie_id}", headers=headers_radarr, json=radarr_movie, timeout=10)
                                    if put_res.status_code in (200, 202):
                                        log(f"✅ Updated Radarr profile to '{target_profile_name}' for: {radarr_movie.get('title')}")
                                        cursor.execute("UPDATE media_files SET radarr_quality_profile = ? WHERE path = ?", (target_profile_name, path))
                                        conn.commit()
                                    else:
                                        log(f"❌ Radarr update failed with status {put_res.status_code}. Skipping local DB update.")
                                else:
                                    cursor.execute("UPDATE media_files SET radarr_quality_profile = ? WHERE path = ?", (target_profile_name, path))
                                    conn.commit()
            except Exception as e:
                log(f"⚠️ [RADARR PROFILE ERROR] {e}")

    sonarr_profile_rules = [r for r in profile_rules if r.get("type") == "sonarr" and r.get("quality_profile", "").strip()]
    if sonarr_profile_rules:
        pending_sonarr_profile_tasks = []
        for idx, rule in enumerate(sonarr_profile_rules):
            target_profile_name = rule.get("quality_profile", "").lower()
            prefixes = rule.get("paths", [])
            path_conditions = " OR ".join([f"path LIKE '{p}/%'" for p in prefixes])

            if target_path:
                query = f"""
                    SELECT path FROM media_files 
                    WHERE path = ? AND (sonarr_quality_profile != ? OR sonarr_quality_profile IS NULL)
                      AND ({path_conditions})
                """
                cursor.execute(query, (target_path, target_profile_name))
            else:
                query = f"""
                    SELECT path FROM media_files 
                    WHERE (sonarr_quality_profile != ? OR sonarr_quality_profile IS NULL)
                      AND ({path_conditions})
                """
                cursor.execute(query, (target_profile_name,))
            rows = cursor.fetchall()
            if rows:
                pending_sonarr_profile_tasks.append((idx, rule, target_profile_name, rows))

        if pending_sonarr_profile_tasks:
            try:
                s_res = requests.get(f"{SONARR_URL}/api/v3/series", headers=headers_sonarr, timeout=15)
                sp_res = requests.get(f"{SONARR_URL}/api/v3/qualityprofile", headers=headers_sonarr, timeout=15)
                if s_res.status_code == 200 and sp_res.status_code == 200:
                    sonarr_series = s_res.json()
                    profiles = sp_res.json()
                    profile_map = {p["name"].lower(): p["id"] for p in profiles}
                    series_path_map = {s["path"].rstrip("/"): s for s in sonarr_series if s.get("path")}

                    for idx, rule, target_profile_name, rows in pending_sonarr_profile_tasks:
                        target_profile_id = profile_map.get(target_profile_name)
                        if not target_profile_id:
                            continue

                        for (path,) in rows:
                            matched_series = None
                            for s_path, s_obj in series_path_map.items():
                                if path.startswith(s_path):
                                    matched_series = s_obj
                                    break
                            
                            if matched_series:
                                series_id = matched_series["id"]
                                current_profile_id = matched_series.get("qualityProfileId")
                                if current_profile_id != target_profile_id:
                                    matched_series["qualityProfileId"] = target_profile_id
                                    put_res = requests.put(f"{SONARR_URL}/api/v3/series/{series_id}", headers=headers_sonarr, json=matched_series, timeout=10)
                                    if put_res.status_code in (200, 202):
                                        log(f"✅ Updated Sonarr profile to '{target_profile_name}' for: {matched_series.get('title')}")
                                        cursor.execute("UPDATE media_files SET sonarr_quality_profile = ? WHERE path = ?", (target_profile_name, path))
                                        conn.commit()
                                    else:
                                        log(f"❌ Sonarr profile update failed with status {put_res.status_code}. Skipping local DB update.")
                                else:
                                    cursor.execute("UPDATE media_files SET sonarr_quality_profile = ? WHERE path = ?", (target_profile_name, path))
                                    conn.commit()
            except Exception as e:
                log(f"⚠️ [SONARR PROFILE ERROR] {e}")

    if unmonitor_rules:
        try:
            if target_path:
                cursor.execute("SELECT path, status, resolution, audio_channels, video_codec, tag FROM media_files WHERE path = ?", (target_path,))
            else:
                cursor.execute("""
                    SELECT path, status, resolution, audio_channels, video_codec, tag 
                    FROM media_files 
                    WHERE (sonarr_unmonitored = 0 OR sonarr_unmonitored IS NULL)
                """)
            rows = cursor.fetchall()
            if rows:
                series_res = requests.get(f"{SONARR_URL}/api/v3/series", headers=headers_sonarr, timeout=15)
                if series_res.status_code == 200:
                    sonarr_series = series_res.json()
                    series_path_map = {s["path"].rstrip("/"): s for s in sonarr_series if s.get("path")}
                    series_cache = {}

                    for rule in unmonitor_rules:
                        prefixes = rule.get("paths", [])
                        fc = rule.get("filter_config", {})
                        target_statuses = fc.get("target_statuses") or ([fc.get("target_status")] if fc.get("target_status") else [])
                        target_tags = fc.get("target_tags", [])

                        for path, status, resolution, audio_channels, v_codec, file_tag in rows:
                            if not any(path.startswith(prefix) for prefix in prefixes):
                                continue
                            if target_statuses and status not in target_statuses:
                                continue
                            if target_tags and not (file_tag and any(t.lower() in file_tag.lower() for t in target_tags)):
                                continue

                            matched_series = None
                            for s_path, s_obj in series_path_map.items():
                                if path.startswith(s_path):
                                    matched_series = s_obj
                                    break
                            if not matched_series:
                                continue

                            series_id = matched_series["id"]
                            try:
                                if series_id not in series_cache:
                                    ep_files_res = requests.get(f"{SONARR_URL}/api/v3/episodefile?seriesId={series_id}", headers=headers_sonarr, timeout=10)
                                    eps_res = requests.get(f"{SONARR_URL}/api/v3/episode?seriesId={series_id}", headers=headers_sonarr, timeout=10)
                                    series_cache[series_id] = {
                                        "episode_files": ep_files_res.json() if ep_files_res.status_code == 200 else [],
                                        "episodes": eps_res.json() if eps_res.status_code == 200 else []
                                    }

                                cached = series_cache[series_id]
                                target_file_id = next((ef.get("id") for ef in cached["episode_files"] if ef.get("path") == path or ef.get("path", "").endswith(os.path.basename(path))), None)
                                
                                if target_file_id:
                                    target_ep_ids = [ep["id"] for ep in cached["episodes"] if ep.get("episodeFileId") == target_file_id and ep.get("monitored", True)]
                                    if target_ep_ids:
                                        bulk_payload = {"episodeIds": target_ep_ids, "monitored": False}
                                        put_ep = requests.put(f"{SONARR_URL}/api/v3/episode/monitor", headers=headers_sonarr, json=bulk_payload, timeout=10)
                                        if put_ep.status_code in (200, 202):
                                            log(f"🛑 [SONARR UNMONITOR] Unmonitored {len(target_ep_ids)} episode(s) for: {matched_series.get('title')}")
                                            cursor.execute("UPDATE media_files SET sonarr_unmonitored = 1 WHERE path = ?", (path,))
                                            conn.commit()
                                        else:
                                            log(f"❌ Sonarr unmonitor failed with status {put_ep.status_code}. Skipping local DB update.")
                            except Exception as e:
                                log(f"⚠️ [UNMONITOR ITEM ERROR] {e}")
        except Exception as e:
            log(f"⚠️ [SONARR UNMONITOR SYNC ERROR] {e}")

    conn.close()

if __name__ == "__main__":
    log(f"🚀 Starting AsyncTranscode-rr Arr Sync Service v{__version__}")
    
    target = sys.argv[1] if len(sys.argv) > 1 else None
    if target:
        log(f"Triggering targeted sync for: {target}")
        run_media_profile_and_unmonitor_sync(target_path=target)
    else:
        log("Triggering global sync for entire library...")
        run_media_profile_and_unmonitor_sync()