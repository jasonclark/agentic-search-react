import re
import httpx
import json
from pathlib import Path

class Agent:
    def __init__(self, system=""):
        self.system = system
        self.messages = []
        # Ollama API endpoint - default local installation
        self.api_url = "http://localhost:11434/api/chat"
        # Can be configured to any Ollama model
        #self.model = "llama3:latest"
        #self.model = "llama3.2:3b-instruct-q2_K"
        #self.model = "qwen3:4b"
        #self.model = "gpt-oss:latest"
        self.model = "phi4-mini:latest"
        #self.model = "gemma3:1b"
        #self.model = "gemma3:4b"
        if self.system:
            self.messages.append({"role": "system", "content": system})
    
    def __call__(self, message):
        self.messages.append({"role": "user", "content": message})
        result = self.execute()
        self.messages.append({"role": "assistant", "content": result})
        return result
    
    def execute(self):
        payload = {
            "model": self.model,
            "messages": self.messages,
            "stream": False
        }
        
        try:
            response = httpx.post(
                self.api_url, 
                json=payload,
                timeout=60.0  # 60 second timeout
            )
            if response.status_code == 200:
                return response.json()["message"]["content"]
            else:
                raise Exception(f"Ollama API error: {response.text}")
        except httpx.ReadTimeout:
            raise Exception("Connection to Ollama timed out. Make sure Ollama is running (ollama serve) and the model is downloaded.")
        except httpx.ConnectError:
            raise Exception("Could not connect to Ollama. Make sure the Ollama server is running (ollama serve).")

# Define the name of your prompt file
prompt_filename = "system-prompt.txt"
# Construct the path and read the file directly
system_prompt = (Path(__file__).parent.parent / "prompts" / prompt_filename).read_text(encoding='utf-8').strip()

action_re = re.compile(r'^Action: (\w+): (.*)$')

def stream_query(question, max_turns=5):
    i = 0
    bot = Agent(system_prompt)
    next_prompt = question
    
    while i < max_turns:
        i += 1
        try:
            result = bot(next_prompt)
            # Split the response to find thoughts and actions
            lines = result.split('\n')
            for line in lines:
                if line.startswith('Thought:'):
                    yield 'thought', line[8:].strip()
                elif line.startswith('Action:'):
                    yield 'action', line[7:].strip()
                    action_match = action_re.match(line)
                    if action_match:
                        action, action_input = action_match.groups()
                        if action not in known_actions:
                            raise Exception(f"Unknown action: {action}: {action_input}")
                        observation = known_actions[action](action_input)
                        yield 'observation', observation
                else:
                    yield 'response', line.strip()
            
            actions = [action_re.match(a) for a in lines if action_re.match(a)]
            if not actions:
                return
                
            action, action_input = actions[0].groups()
            observation = known_actions[action](action_input)
            next_prompt = f"Observation: {observation}"
            
        except Exception as e:
            yield 'error', str(e)
            return

def wikipedia(query):
    """Fetches a summary from Wikipedia.

    Args:
      query: The search query for Wikipedia.

    Returns:
      A dictionary with either a 'result' key containing the summary or an 'error' key.
    """
    response = httpx.get("https://en.wikipedia.org/w/api.php", params={
        "action": "query",
        "list": "search",
        "srsearch": query,
        "format": "json"
    })

    if not response.is_success:
        return {"error": f"Error fetching Wikipedia data: {response.status_code} {response.reason_phrase}"}

    try:
        data = response.json()
    except json.JSONDecodeError:
        return {"error": "Invalid JSON response from Wikipedia"}

    if not data.get("query", {}).get("search", []):
        return {"error": f"No Wikipedia results found for '{query}'"}

    return {"result": data["query"]["search"][0]["snippet"]}

def wikidata(query):
    """Fetches information from Wikidata.

    Args:
      query: The search query for Wikidata.

    Returns:
      A dictionary with either a 'result' key containing the information or an 'error' key.
    """
    response = httpx.get("https://www.wikidata.org/w/api.php", params={
        "action": "wbsearchentities",
        "search": query,
        "format": "json",
        "language": "en",
        "uselang": "en",
        "type": "item",
        "limit": 1
    })

    if not response.is_success:
        return {"error": f"Error fetching Wikidata data: {response.status_code} {response.reason_phrase}"}

    try:
        data = response.json()
    except json.JSONDecodeError:
        return {"error": "Invalid JSON response from Wikidata"}

    if not data.get("search", []):
        return {"error": f"No Wikidata results found for '{query}'"}

    result = data["search"][0]
    return {"result": f"{result['label']}: {result.get('description', 'No description available')}" }

def search_msu_expertise(query):
    """Performs a search for MSU expertise and researcher interests.

    Args:
      query: The search query in the custom search engine.

    Returns:
      A dictionary containing a list of dictionaries, where each inner 
      dictionary contains 'title', 'link', and 'snippet' for each search result.
    """
    #set up your own Discovery Engine and Vertex AI Search
    #https://docs.cloud.google.com/generative-ai-app-builder/docs/migrate-from-cse
    projectID = 'ADD-YOUR-PROJECT-DATASTORE-ID'
    agentID = 'ADD-YOUR-AGENT-ID'
    apiKey = 'ADD-YOUR-API-KEY'
    
    url = f"https://discoveryengine.googleapis.com/v1/projects/{projectID}/locations/global/collections/default_collection/engines/{agentID}/servingConfigs/default_search:searchLite?key={apiKey}"
    
    data = {
        "servingConfig": f"projects/{projectID}/locations/global/collections/default_collection/engines/{agentID}/servingConfigs/default_search",
        "query": query,
        "contentSearchSpec": {
            "summarySpec": {
                "summaryResultCount": 3,
                "includeCitations": True
            },
            "extractiveContentSpec": {
                "maxExtractiveAnswerCount": 1
            }
        }
    }

    response = httpx.post(url, json=data)

    if not response.is_success:
        return {"error": f"Error fetching Google Search results: {response.status_code} {response.reason_phrase}"}

    try:
        decoded_response = response.json()
    except json.JSONDecodeError:
        return {"error": "Invalid JSON response from Google Search"}

    # Extract and format search results
    results = []
    for result in decoded_response.get('results', []):
        extracted_result = {
            'title': result['document']['derivedStructData']['title'],
            'link': result['document']['derivedStructData']['link'],
            'snippet': result['document']['derivedStructData']['snippets'][0]['snippet']
        }
        results.append(extracted_result)

    decoded_response['results'] = results
    return decoded_response

known_actions = {
    "wikipedia": wikipedia,
    "search_msu_expertise": search_msu_expertise,
    "wikidata": wikidata
}