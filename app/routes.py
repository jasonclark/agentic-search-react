from flask import Blueprint, render_template, request, jsonify, Response, stream_with_context
from app.agent import stream_query
import json

main = Blueprint('main', __name__)

@main.route('/')
def index():
    return render_template('index.html')

@main.route('/ask', methods=['POST'])
def ask():
    data = request.get_json()
    question = data.get('question')
    if not question:
        return jsonify({'error': 'No question provided'}), 400

    def generate_responses():
        try:
            for response_type, content in stream_query(question):
                yield f"data: {json.dumps({'type': response_type, 'content': content})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return Response(stream_with_context(generate_responses()), 
                   mimetype='text/event-stream')