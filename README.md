# Navidrome Discord Rich Presence (NavRPC) 🎧

**NavRPC** is a lightweight, optimized Python script that updates your Discord status to display the song currently playing on your [Navidrome](https://www.navidrome.org/) server. It features an integrated Imgur cache and intelligent image optimization to ensure album art displays correctly on Discord.

## 📷 Example

<img width="226" height="58" alt="d32eceac-14c5-4b3d-bfbb-943d5f62f748" src="https://github.com/user-attachments/assets/c78fd59e-7a38-444e-99dc-da7bb4515e57" />
<br>
<img width="452" height="192" alt="33077796-a82b-4eac-a379-02b96434977a" src="https://github.com/user-attachments/assets/157a9a0d-0962-4b4a-8292-27730dce1470" />

## ✨ Features

* **Subsonic API Polling:** Connects directly to the Navidrome API to fetch the current track.
* **Intelligent Caching:** Uploads and caches album art (via Imgur) locally.
* **Resource Friendly:** Optimized for low CPU/RAM usage, ideal for running on a server, NAS, or Raspberry Pi.
* **Timestamp Accuracy:** Calculates track start and end times to display the remaining time accurately. Note: Can be inaccurate.

## 🚀 Setup

### 1. Prerequisites

You need **Python 3.8+** installed on your system.

### 2. Installation

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/zeroquinc/navrpc.git](https://github.com/zeroquinc/navrpc.git)
    cd navrpc
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

### 3. Configuration

You must set up your API keys and Navidrome server details.

1.  **Create the config file:**
    ```bash
    cp config.yaml.example config.yaml
    ```

2.  **Edit `config.yaml`** and fill in the required fields:

    | Section | Key | Description |
    | :--- | :--- | :--- |
    | `navidrome` | `base_url` | The URL to your Navidrome REST endpoint (e.g., `http://192.168.0.150:4533/rest`). |
    | | `username` | Your Navidrome username. |
    | | `password` | Your Navidrome password. |
    | `integration` | `imgur_client_id` | **Required.** Get a free client ID from [Imgur's API page](https://api.imgur.com/oauth2/addclient). |
    | | `discord_client_id` | **Required.** Your Discord Application ID. **MUST BE QUOTED.** |
    | | `discord_asset_name` | *Optional.* The name of a custom asset uploaded to your Discord App (e.g., a Navidrome logo). Used as a fallback if album art fails. |
    | `general` | `poll_interval_seconds` | How often (in seconds) to check for new tracks. Default: `5`. |
    | | `cache_file` | Path to the local cache file. Default: `cache.json`. |
    | | `strip_title_subtitle` | Remove subtitles from track titles (e.g., "(Explicit)", "(Remastered)"). Default: `true`. |
    | `image` | `max_size` | Maximum width/height for album art. Default: `512`. |
    | | `jpeg_quality` | JPEG compression quality (1-100). Default: `85`. |
    | | `max_file_bytes` | Maximum file size in bytes. Default: `4194304` (4MB). |

    **⚠️ Important: Quote the Discord Client ID**
    Ensure your `discord_client_id` is enclosed in quotes to be read as a string:
    ```yaml
    integration:
      discord_client_id: '11907920212632236732'
    ```

## ⚙️ Usage

### Running Manually

Execute the entry point script from the project root:

```bash


python run.py
