import os
import sys
import json
import time
import requests
from pydub import AudioSegment
from urllib.parse import quote

# Configuration
TALK_GROUPS = [
    {"id": "22012", "name": "FireDispatch"},
    # {"id": "21500", "name": "Patrol 1"},
    # {"id": "21501", "name": "Patrol 2"},
    # {"id": "22016", "name": "Arrow OPS1"},
    # {"id": "22000", "name": "Fire OPS 1"},
    # {"id": "22006", "name": "FireGround 5"},
]

PROMPT = "Champaign, Urbana, Allerton, Bondville, Broadlands, Fisher, Foosland, Gifford, Homer, Ivesdale, Longview, Ludlow, Mahomet, Ogden, Pesotum, Philo, Rantoul, Royal, Sadorus, St. Joseph, Savoy, Seymour, Sidney, Thomasboro, Tolono, Dewey, Lake of the Woods, Flatville, Prospect, Rising, Rutherford, Sellers, Staley, State Road, Tipton, Tomlinson, Wilbur Heights, County Road, METCAD, engine, ladder, fire ops, fire ground, fire alarm, AMT, Arrow, Medic, alpha level, bravo level, charley level, delta level, echo level, sick person, lift assist, chest pain, full arrest, Accident with injuries, working fire, Medical, METCAD clear, cross streets, channel assignment, alpha response, bravo response, charley response, delta response, echo response, its a"
PROMPT_CLEAN = quote(PROMPT)

# Whisper API Configuration
URL = "transcribe_url"
WHISPER_CONFIG_DATA = {
    "language": "en",
    "beam_size": 5,
    "best_of": 5,
    "initial_prompt": PROMPT,
    "use_last_as_initial_prompt": False,
    "word_timestamps": False,
    "vad_filter": True,
    "vad_parameters": {
        "threshold": 0.3,
        "min_speech_duration_ms": 250,
        "max_speech_duration_s": 3600,
        "min_silence_duration_ms": 1000,
        "speech_pad_ms": 400,
    },
}

SLACK_WEBHOOK_URL = "SLACK_WEBHOOK"  # Replace with your Slack Webhook URL
DISCORD_WEBHOOK_URL = "DISCORD_WEBHOOK"  # Replace with your Discord Webhook URL
SLACK = True
DISCORD = True

RATE = 0.8
TIMESTAMP_FILE = "/dev/shm/delete_timestamp.txt"


def send_http_post(url, headers, body):
    response = requests.post(url, headers=headers, json=body)
    return response.status_code, response.text


def send_to_slack(talk_group_name, message):
    payload = {"text": f"*Talk Group: {talk_group_name}*\n{message}"}
    headers = {"Content-Type": "application/json"}
    status, response = send_http_post(SLACK_WEBHOOK_URL, headers, payload)
    print("Slack Response:", response)


def send_to_discord(talk_group_name, message):
    payload = {"content": f"**Talk Group: {talk_group_name}**\n{message}"}
    headers = {"Content-Type": "application/json"}
    status, response = send_http_post(DISCORD_WEBHOOK_URL, headers, payload)
    print("Discord Response:", response)


def slow_down_audio(filepath):
    slowed_filepath = filepath.replace(".wav", "_slowed.wav")
    try:
        audio = AudioSegment.from_file(filepath)
        slowed_audio = audio._spawn(
            audio.raw_data, overrides={"frame_rate": int(audio.frame_rate * RATE)}
        ).set_frame_rate(audio.frame_rate)
        slowed_audio.export(slowed_filepath, format="wav")
        return slowed_filepath
    except Exception as e:
        print(f"Error slowing down audio: {e}")
        return filepath


def post_audio(audio_file_path, url, config_data):
    try:
        config_json_string = json.dumps(config_data)
        data = {"whisper_config_data": config_json_string}
        with open(audio_file_path, "rb") as audio_file:
            files = {"audioFile": audio_file}
            response = requests.post(url, files=files, data=data)
            response_data = response.json()
            return response_data.get("transcript", "")
    except Exception as e:
        print(f"Error during the request: {e}")
        return ""


def should_delete_old_files():
    if os.path.exists(TIMESTAMP_FILE):
        with open(TIMESTAMP_FILE, "r") as f:
            last_run = float(f.read().strip())
        return time.time() - last_run > 600
    return True


def update_timestamp():
    with open(TIMESTAMP_FILE, "w") as f:
        f.write(str(time.time()))


def delete_old_files(directory_path="/dev/shm/metcadbak", threshold=300):
    if not should_delete_old_files():
        return

    current_time = time.time()
    for dirpath, dirnames, filenames in os.walk(directory_path):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            file_age = current_time - os.path.getmtime(file_path)
            if file_age > threshold:
                os.remove(file_path)
                print(f"Deleted: {file_path}")
    update_timestamp()


def process_file(filepath):
    if not os.path.isfile(filepath):
        print(f"Error: File '{filepath}' does not exist.")
        return

    matching_talk_groups = [tg for tg in TALK_GROUPS if tg["id"] in filepath]
    if not matching_talk_groups:
        return

    talk_group_name = matching_talk_groups[0]["name"]
    slowed_filepath = slow_down_audio(filepath)
    transcript = post_audio(slowed_filepath, URL, WHISPER_CONFIG_DATA)
    print(f"Transcript for {talk_group_name}: {transcript}")

    if SLACK:
        send_to_slack(talk_group_name, transcript)
    if DISCORD:
        send_to_discord(talk_group_name, transcript)

    delete_old_files()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py <file_path>")
        sys.exit(1)
    process_file(sys.argv[1])
