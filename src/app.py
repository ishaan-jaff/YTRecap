# Import necessary libraries
import os
import openai
from flask import Flask, render_template, request
from youtube_transcript_api import YouTubeTranscriptApi, CouldNotRetrieveTranscript
import re
from googleapiclient.discovery import build
import datetime
import isodate
from dotenv import load_dotenv

# Initialize Flask app and load environment variables
app = Flask(__name__)
load_dotenv()

# Set OpenAI API key
openai.api_key = os.environ.get('OPENAI_KEY')

# Function to format duration string into a human-readable format
def format_duration(duration_string):
    duration = isodate.parse_duration(duration_string)
    total_seconds = int(duration.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"

# Function to format view count into a human-readable format
def format_view_count(view_count):
    view_count = int(view_count)
    if view_count >= 1000000:
        return f"{view_count // 1000000}M"
    elif view_count >= 10000:
        return f"{view_count // 1000}K"
    else:
        return str(view_count)

# Function to format date string into a human-readable format
def format_date(date_string):
    date = datetime.datetime.fromisoformat(date_string[:-1])
    return date.strftime("%B %d, %Y")

# Function to parse transcript and extract text information
def parse_text_info(input_list):
    #regex to remove timestamps and speaker names
    pattern = re.compile(r"'text':\s+'(?:\[[^\]]*\]\s*)?([^']*)'")
    output = ""
    for item in input_list:
        match = pattern.search(str(item))
        if match:
            text = match.group(1).strip()
            text = text.replace('\n', ' ')
            text = re.sub(' +', ' ', text)
            output += text + " "
    return output.strip()


# Function to generate summary using OpenAI API
def generateSummaryWithCaptions(captions, summary_length, yt_url, yt_title):
    # Set default length to 200 tokens
    # Set summary length to default value if user does not select a summary length
    try:
        if summary_length > 500:
            prompt = f"Can you provide a very long and in-depth summary on this YouTube video based on the closed captions provided here:\n\n {captions}\n\nHere is the video link: {yt_url} along with its title: {yt_title}"
        else:
            prompt = f"Can you provide a summary on this YouTube video based on the closed captions provided here:\n\n {captions}\n\nPlease keep it to approximately {summary_length} words.\n\nHere is the video link: {yt_url} along with its title: {yt_title}"
            
        response = openai.Completion.create(
            engine="text-davinci-003",
            prompt=prompt,
            max_tokens= 1500,
            n=1,
            stop=None,
            temperature=0.5,
        )
        # Remove newlines and extra spaces from summary
        summary = response.choices[0].text.strip()
        return summary

    except openai.error.InvalidRequestError:
        # Return error message if summary cannot be generated
        # summary = "Uh oh! Sorry, we couldn't generate a summary for this video due to the video being too long. Please try a shorter video, this model handles videos up to 30 minutes in length with a 1000 length summary"
        summaryNoCaptions = generateSummaryNoCaptions(summary_length, yt_url, yt_title)
        return summaryNoCaptions


#  - This is a fallback function to generate a summary when no captions are provided by YouTube
# - This function is called when the video is too long (causes character limit to openAI API, or there are no captions)
def generateSummaryNoCaptions(summary_length, url, yt_title):
    if summary_length > 500: 
        prompt = f"Can you write an very long in depth summary about this video {url} in approximately {summary_length} words. The title of the video is {yt_title}?"
    else:
        prompt = f"Can you write a summary about this video {url} in approximately {summary_length} words. The title of the video is {yt_title}?"

    print("Parsing API without captions due to long video OR not captions (or both)...")
    response = openai.Completion.create(
        engine="text-davinci-003",
        prompt=prompt,
        max_tokens= 1500,
        n=1,
        stop=None,
        temperature=0.5,
    )
    # Remove newlines and extra spaces from summary
    summary = response.choices[0].text.strip()
    return summary

# Render index page
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def index(path):
    return render_template('index.html')

# Get transcript and generate summary
@app.route('/', methods=['POST'], defaults={'path': ''})
@app.route('/<path:path>', methods=['POST'])
# Get transcript and generate summary
@app.route('/', methods=['POST'], defaults={'path': ''})
@app.route('/<path:path>', methods=['POST'])
def get_transcript(path):
    # Get video URL from user input
    url = request.form['url']
    # Extract video ID from URL using regex
    match = re.search(r"(?<=v=)[\w-]+|[\w-]+(?<=/v/)|(?<=youtu.be/)[\w-]+", url)
    # If match is found, get video information from YouTube API
    if match:
        video_id = match.group(0)
        youtube = build('youtube', 'v3', developerKey=os.environ.get('YT_KEY'))
        video_response = youtube.videos().list(
            part='snippet,statistics',
            id=video_id
        ).execute()
        
        # Extract video information
        video_info = {
            'title': video_response['items'][0]['snippet']['title'],
            'author': video_response['items'][0]['snippet']['channelTitle'],
            'date': format_date(video_response['items'][0]['snippet']['publishedAt']),
            'view_count': format_view_count(video_response['items'][0]['statistics']['viewCount']),
            'thumbnail': video_response['items'][0]['snippet']['thumbnails']['medium']['url'],
        }
    # Get transcript and parse text
    yt_title = video_response['items'][0]['snippet']['title']
    summary_length = int(request.form['summary_length'])
    try: 
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        captions = parse_text_info(transcript)
    except:
        captions = None
        
    if captions:
        summary = generateSummaryWithCaptions(captions, summary_length, url, yt_title)
    else:
        summary = generateSummaryNoCaptions(summary_length, url, yt_title)

    # Render the result in the template
    return render_template('index.html', video_info=video_info, summary=summary, video_id=video_id, summary_length=summary_length)

# Run Flask app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
