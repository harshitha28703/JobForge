from flask import Flask, render_template, request
from openai import OpenAI
from flask_socketio import SocketIO, emit
import speech_recognition as sr
import pyttsx3
import threading
import time

openai_api_key = "ADD_API_KEY"
client = OpenAI(api_key=openai_api_key)
app = Flask(__name__)
socketio = SocketIO(app)

conversation_data = []
grades_list = []  # New list to store user grades

def get_speech_input():
    recognizer = sr.Recognizer()

    with sr.Microphone() as source:
        print("Say something:")
        recognizer.adjust_for_ambient_noise(source)

        # Start listening
        audio = recognizer.listen(source, timeout=None)

    start_time = time.time()

    try:
        # Recognize speech and print the result
        text = recognizer.recognize_google(audio)
        print("You said:", text)
        return text
    except sr.UnknownValueError:
        print("Could not understand audio.")
        return ""
    except sr.RequestError as e:
        print(f"Could not request results from Google Speech Recognition service; {e}")
        return ""
    finally:
        # Stop listening 3 seconds after the user stops talking
        elapsed_time = time.time() - start_time
        timeout = max(0, 2 - elapsed_time)
        time.sleep(timeout)


def text_to_speech(text):
    engine = pyttsx3.init()
    engine.say(text)
    engine.runAndWait()


def chat_with_openai(user_prompt, max_words=50):
    conversation = [
        {"role": "system", "content": "You are a technical assistant, skilled in explaining programming concepts. Ask only simple tech-related interview questions. Do not ask the user what topic they would like, or any other questions. Every question must be different."},
        {"role": "user", "content": user_prompt},
    ]

    completion = client.chat.completions.create(
        model="gpt-3.5-turbo-1106",
        messages=conversation
    )

    assistant_prompt = completion.choices[0].message.content

    return assistant_prompt


def evaluate_answer(user_answer):
    # Use the ChatGPT API to generate a grade for the user's answer
    prompt = f"Evaluate the following user answer: {user_answer}"

    response = client.chat.completions.create(
        model="gpt-3.5-turbo-1106",
        messages=[
            {"role": "system", "content": "You are an interviewer with a unique communication style. Use a 2-degree Bridge-building style to provide an alphabetic grade only.If the answer is in no way correct, let the grade be F.Mention correct answer if grade is F."},
            {"role": "user", "content": prompt}
        ]
    )

    # Extract the generated grade from the response
    generated_grade = response.choices[0].message.content.strip()
    # Create the truncated response by including sentences within the word limit
    sentences = generated_grade.split('.')

    truncated_response = ''
    current_words = 0
    for sentence in sentences:
        sentence_words = sentence.split()
        if current_words + len(sentence_words) <= 30:
            truncated_response += sentence + '.'
            current_words += len(sentence_words)
        else:
            break

    return truncated_response


@app.route('/')
def index():
    return render_template('index.html')


@socketio.on('get_conversation')
def handle_get_conversation():
    emit('update_conversation', {'conversation': conversation_data, 'grades': grades_list})


# New route for exiting the application
@app.route('/exit', methods=['GET'])
def exit_app():
    print("Exiting the application.")
    socketio.stop()
    return 'Application exited successfully'


# Add the route for processing user input
@app.route('/process', methods=['POST'])
def process():
    while True:
        # Perform OpenAI chat
        if not conversation_data:
            assistant_reply = chat_with_openai("Let's Start")
        else:
            assistant_reply = chat_with_openai(user_prompt)

        # Convert assistant's reply to speech
        text_to_speech(assistant_reply)

        # Emit the updated conversation to the clients
        socketio.emit('update_conversation', {'conversation': conversation_data, 'grades': grades_list}, namespace='/')

        # Get user's prompt
        user_prompt = get_speech_input()

        # Check if the user wants to exit
        if user_prompt.lower() in ('exit', 'goodbye', 'leave'):
            print("Exiting the conversation.")
            result = "exiting"
            break
        else:
            user_grade = evaluate_answer(user_prompt)

            # Update conversation data with the user's prompt, assistant's reply, and grade
            conversation_data.append({"assistant": assistant_reply, "user": user_prompt, "grade": user_grade})
            grades_list.append(user_grade)  # Update the grades_list with the actual grade

            # Emit the updated conversation and grades to the clients
            socketio.emit('update_conversation', {'conversation': conversation_data, 'grades': grades_list}, namespace='/')

            result = render_template('index.html', conversation=conversation_data, grades=grades_list)

        # Move the loop continuation condition here
        if result == "exiting":
            break

    return result


if __name__ == "__main__":
    socketio.run(app, debug=True)
