import time
import threading
import numpy as np
from datetime import datetime
from flask import Flask, render_template, request, jsonify
import speech_recognition as sr  # Import Google STT
import os
from twilio.rest import Client  # Import Twilio API

app = Flask(__name__)

# --- Twilio Credentials ---
ACCOUNT_SID = #Replace with your Twilio account SID
AUTH_TOKEN = #Replace with your Twilio authentication token
TWILIO_PHONE_NUMBER = # Replace with your Twilio number
USER_PHONE_NUMBER = # Replace with recipient's phone number

# --- Scam Keyword Setup ---
scam_keywords = ["otp", "bank", "account", "card", "aadhar"]
alert_messages = {
    "otp": "⚠️ ALERT: Banks never ask for your OTP via call or SMS.",
    "bank_account": "⚠️ ALERT: Banks do not ask for your full account number.",
    "aadhaar": "⚠️ ALERT: Never share your full Aadhaar number.",
}

# --- Globals ---
is_listening = False
transcriptions = []
alerts = []
data_lock = threading.Lock()
recognizer = sr.Recognizer()

# --- Twilio SMS Function ---
def send_sms(message):
    """ Sends an SMS alert using Twilio API """
    client = Client(ACCOUNT_SID, AUTH_TOKEN)
    try:
        sms = client.messages.create(
            body=message,
            from_=TWILIO_PHONE_NUMBER,
            to=USER_PHONE_NUMBER
        )
        print(f"✅ SMS sent! SID: {sms.sid}")
    except Exception as e:
        print(f"❌ Failed to send SMS: {e}")

# --- Scam Detection ---
def detect_scam_keywords(text):
    #Detects scam-related keywords and sends alerts
    for keyword in scam_keywords:
        if keyword in text.lower():
            alert_message = alert_messages.get(keyword, " Possible scam detected! ⚠️")
            send_sms(alert_message)  # Send SMS alert
            generate_report()
            return alert_message
    return None

def process_text(text):
    """ Process transcribed text and detect scams """
    print(f"Processed Text: {text}")
    alert_message = detect_scam_keywords(text)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    transcription_entry = {"speaker": "Speaker", "text": text, "timestamp": timestamp}
    
    with data_lock:
        transcriptions.append(transcription_entry)
        if alert_message:
            alerts.append({"message": alert_message, "timestamp": timestamp})

# --- Background Listening (Speech Recognition) ---
def background_listener(selected_language="en-US"):
    global is_listening
    with sr.Microphone() as source:
        print(f"Listening in {selected_language}...")
        recognizer.adjust_for_ambient_noise(source)

        while is_listening:
            try:
                print("\nListening...")
                audio = recognizer.listen(source)
                text = recognizer.recognize_google(audio, language=selected_language)
                print("You said:", text)
                process_text(text)  # Process speech text
            except sr.UnknownValueError:
                print("Sorry, could not understand.")
            except sr.RequestError:
                print("Could not request results from Google STT API.")

            time.sleep(0.1)

# --- Flask Routes ---
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/start", methods=["POST"])
def start_listening():
    global is_listening
    selected_language = request.json.get("language", "en-US")
    if not is_listening:
        is_listening = True
        threading.Thread(target=background_listener, args=(selected_language,), daemon=True).start()
    return jsonify({"status": "Listening started", "language": selected_language})

@app.route("/stop", methods=["POST"])
def stop_listening():
    global is_listening
    is_listening = False
    generate_report()  # Send transcript via SMS
    return jsonify({"status": "Listening stopped"})

@app.route("/updates", methods=["GET"])
def updates():
    with data_lock:
        new_transcriptions = transcriptions.copy()
        new_alerts = alerts.copy()
        alerts.clear()
    return jsonify({
        "transcriptions": new_transcriptions,
        "alerts": new_alerts
    })

# --- Generate Report & Send SMS ---
def generate_report():
    """ Generates a transcript report and sends it via SMS """
    with data_lock:
        if not transcriptions:
            print("No conversation recorded.")
            return
        
        transcript_text = "📞 Here's the summary of your conversation. No Scam Keywords Detected ✅\nConversation Transcript:\n\n"
        for entry in transcriptions:
            transcript_text += f"[{entry['timestamp']}] {entry['speaker']}: {entry['text']}\n"

    print("Sending transcript via SMS...")
    
    # Twilio has a character limit per SMS (1600 chars). Send in chunks if necessary.
    max_sms_length = 1600
    if len(transcript_text) > max_sms_length:
        chunks = [transcript_text[i:i+max_sms_length] for i in range(0, len(transcript_text), max_sms_length)]
        for chunk in chunks:
            send_sms(chunk)
    else:
        send_sms(transcript_text)

    print("Transcript sent successfully!")

if __name__ == "__main__":
    app.run(debug=True)
