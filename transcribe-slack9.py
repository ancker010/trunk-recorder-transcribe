import os
import sys
import ftplib
import http.client
import time
from urllib.parse import urlparse
from pydub import AudioSegment

# Configuration
TALK_GROUPS = [
    #    {"id": "21500", "name": "Patrol 1"},
    #    {"id": "22016", "name": "Arrow OPS1"},
    #    {"id": "22000", "name": "Fire OPS 1"},
    #    {"id": "22006", "name": "FireGround 5"},
    {"id": "22012", "name": "FireDispatch"},
]  # Replace with the list of talk group IDs and names
UPLOAD_URL = "URL"  # Replace with your URL endpoint
SLACK_WEBHOOK_URL = "SLACK_WEBHOOK"  # Replace with your Slack Webhook URL
DISCORD_WEBHOOK_URL = "DISCORD_WEBHOOK"  # Replace with your Discord Webhook URL
SLACK = True
DISCORD = True
RATE = 0.8


def upload_to_ftp(filepath):
    FTP_SERVER = "ftp-server"
    FTP_USERNAME = "ftp-user"
    FTP_PASSWORD = "password"
    FTP_UPLOAD_PATH = "/Storage/ftp"

    try:
        with ftplib.FTP(FTP_SERVER) as ftp:
            ftp.login(FTP_USERNAME, FTP_PASSWORD)
            ftp.cwd(FTP_UPLOAD_PATH)

            with open(filepath, "rb") as file:
                ftp.storbinary(f"STOR {os.path.basename(filepath)}", file)
                #print(f"Successfully uploaded {filepath} to FTP")
    except Exception as e:
        print(f"FTP upload failed: {e}")


# delete files from a directory if they're older than 5 minutes
def delete_files():
    directory_path = "/dev/shm/metcadbak"

    # Get the current time
    current_time = time.time()

    # Set the time threshold (10 minutes = 600 seconds)
    threshold = 300

    # Loop through the files in the directory
    for dirpath, dirnames, filenames in os.walk(directory_path):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)

            # Get the file's last modification time
            file_age = current_time - os.path.getmtime(file_path)

            # If the file is older than 10 minutes, delete it
            if file_age > threshold:
                os.remove(file_path)
                print(f"Deleted: {file_path}")


# Helper function to send HTTP POST requests
def send_http_post(url, headers, body):
    parsed_url = urlparse(url)
    connection = (
        http.client.HTTPSConnection(parsed_url.netloc)
        if parsed_url.scheme == "https"
        else http.client.HTTPConnection(parsed_url.netloc)
    )
    connection.request(
        "POST",
        parsed_url.path + ("?" + parsed_url.query if parsed_url.query else ""),
        body,
        headers,
    )
    response = connection.getresponse()
    return response.status, response.read().decode()


# Function to send a message to Slack
def send_to_slack(talk_group_name, message):
    payload = {"text": f"*Talk Group: {talk_group_name}*\n{message}"}
    headers = {"Content-Type": "application/json"}
    body = str(payload)
    status, response = send_http_post(SLACK_WEBHOOK_URL, headers, body)
    if status == 200:
        print("Successfully sent message to Slack.")
    else:
        print(f"Failed to send message to Slack: {status} {response}")


# Function to send a message to Discord
def send_to_discord(talk_group_name, message):
    import json  # Import json to ensure proper JSON encoding

    payload = {"content": f"**Talk Group: {talk_group_name}**\n{message}"}
    headers = {"Content-Type": "application/json"}
    body = json.dumps(payload)  # Use json.dumps for strict JSON formatting
    status, response = send_http_post(DISCORD_WEBHOOK_URL, headers, body)
    if status == 204:
        print("Successfully sent message to Discord.")
    else:
        print(f"Failed to send message to Discord: {status} {response}")


# Function to slow down playback speed by half
def slow_down_audio(filepath):
    slowed_filepath = filepath.replace(".wav", "_slowed.wav")
    try:
        # Load the audio file
        audio = AudioSegment.from_file(filepath)
        # Slow down playback speed
        slowed_audio = audio._spawn(
            audio.raw_data, overrides={"frame_rate": int(audio.frame_rate * RATE)}
        )
        slowed_audio = slowed_audio.set_frame_rate(audio.frame_rate)
        # Export the slowed-down audio
        slowed_audio.export(slowed_filepath, format="wav")
        print(f"Audio slowed down and saved to {slowed_filepath}")
        return slowed_filepath
    except Exception as e:
        print(f"Error slowing down audio: {e}")
        return filepath  # Fall back to original file if processing fails


# Updated function to upload a file
def upload_file(filepath, talk_group_name):
    slowed_filepath = slow_down_audio(filepath)

    filename = os.path.basename(slowed_filepath)
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    with open(slowed_filepath, "rb") as file:
        file_data = file.read()

    body = (
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="audio_file"; filename="{filename}"\r\n'
            f"Content-Type: audio/x-m4a\r\n\r\n"
        ).encode("utf-8")
        + file_data
        + f"\r\n--{boundary}--\r\n".encode("utf-8")
    )

    status, response = send_http_post(UPLOAD_URL, headers, body)
    if status == 200:
        print(f"Successfully uploaded {filename}")
        if SLACK:
            send_to_slack(talk_group_name, response)
        if DISCORD:
            send_to_discord(talk_group_name, response)
        return True
    else:
        print(f"Failed to upload {filename}: {status} {response}")
        return False


# Main function to process a single file
def main():
    if len(sys.argv) < 2:
        print("Usage: python script.py <file_path>")
        sys.exit(1)

    filepath = sys.argv[1]
    json_file = sys.argv[2]
    #    filepath = sys.argv[3]

    if not os.path.isfile(filepath):
        print(f"Error: File '{filepath}' does not exist.")
        sys.exit(1)

    # Upload to FTP
    # upload_to_ftp(filepath)

    # Check if the file belongs to any of the specified talk groups
    matching_talk_groups = [tg for tg in TALK_GROUPS if tg["id"] in filepath]
    talk_group_name = (
        matching_talk_groups[0]["name"] if matching_talk_groups else sys.exit()
    )

    # Upload the file
    if upload_file(filepath, talk_group_name):
        try:
            delete_files()
            print(f"Deleted files")
        except Exception as e:
            print(f"Error deleting file: {e}")
    else:
        # If the time is a 0, 15, 30, or 45, then delete_files()
        if time.localtime().tm_min % 15 == 0:
            try:
                delete_files()
                print(f"Deleted files: Auto cleanup on the 15s")
            except Exception as e:
                print(f"Error deleting file: {e}")


if __name__ == "__main__":
    main()
